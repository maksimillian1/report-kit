"""OpenCost's prices for a window held against AWS's: what is read back from
Prometheus, what AWS is asked, when a point is put in doubt, and how the point
record, the journal and the verdict carry it.

    pytest tests/test_price_check.py

Every name and number here is invented, rates included. Prometheus and AWS
are the two `shell` seams, patched; nothing reaches a network.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from report_kit import finish, opencost, price_check
from report_kit import point as points
from report_kit.execution_config import PointPlan, Setting
from report_kit.preflight import Preflight
from report_kit.cloud import aws
from report_kit.constants import EXIT_CLEAN, EXIT_SUSPECT
from report_kit.execution_config import ExecutionError, PriceMatch, parse_execution
from report_kit.register import parse_register
from report_kit.tools.values.points import validity_problems
from report_kit.window import Window

START = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc).timestamp()
WINDOW = Window(datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 1, 2, 10, 10, tzinfo=timezone.utc))
ALL_LINES = [opencost.NODES, opencost.VOLUMES, opencost.LOAD_BALANCERS,
             opencost.CONTROL_PLANE]
REGION, ZONE, LOCATION = "eu-central-1", "eu-central-1a", "EU (Frankfurt)"


def held(value: str, *later: str) -> list:
    """Samples a minute apart: `value` first, then each of `later`."""
    return [[START + 60 * i, v] for i, v in enumerate((value, *later))]


def node(name: str, price: str, *, kind: str = "m6i.large",
         provider: str = f"aws:///{ZONE}/i-0abc", region: str = REGION) -> dict:
    return {"metric": {"node": name, "instance_type": kind, "region": region,
                       "provider_id": provider}, "values": held(price, price)}


class Prometheus:
    """Answers each query opencost.py sends, from series given per line."""

    def __init__(self, nodes=(), spot=(), volumes=(), balancers=(), plane=(),
                 unpriced=(), regions=(REGION,)):
        self.ranges = {opencost.LINE_QUERIES[opencost.NODES]: list(nodes),
                       opencost.SPOT_QUERY: [{"metric": {"node": n}, "values": held("1")}
                                             for n in spot],
                       opencost.LINE_QUERIES[opencost.VOLUMES]: list(volumes),
                       opencost.LINE_QUERIES[opencost.LOAD_BALANCERS]: list(balancers),
                       opencost.LINE_QUERIES[opencost.CONTROL_PLANE]: list(plane)}
        self.unpriced = unpriced
        self.regions = regions

    def http_json(self, method, url, body=None, timeout=30):
        query = parse_qs(urlparse(url).query)["query"][0]
        if "/api/v1/query_range" in url:
            return {"status": "success", "data": {"result": self.ranges[query]}}
        if "kube_node_info" in query:
            result = [{"metric": {"node": n}, "value": [0, "1"]} for n in self.unpriced]
        else:
            result = [{"metric": {"region": r}, "value": [0, "1"]} for r in self.regions]
        return {"status": "success", "data": {"result": result}}


def listed(usage: str, usd: str, unit: str = "Hrs", **attributes) -> dict:
    return {"usagetype": usage, "location": LOCATION, "unit": unit, "usd": usd,
            **attributes}


CATALOG = {
    "AmazonEC2": [
        listed("EUC1-BoxUsage:m6i.large", "0.1000", instanceType="m6i.large",
               operatingSystem="Linux", tenancy="Shared", preInstalledSw="NA",
               capacitystatus="Used"),
        listed("EUC1-EBS:VolumeUsage.gp3", "0.0950", "GB-Mo", productFamily="Storage",
               volumeApiName="gp3"),
        listed("EUC1-EBS:VolumeP-IOPS.gp3", "0.0060", "IOPS-Mo",
               productFamily="System Operation", volumeApiName="gp3"),
    ],
    "AWSELB": [
        listed("EUC1-LoadBalancerUsage", "0.0270", productFamily="Load Balancer-Network"),
        listed("EUC1-LCUUsage", "0.0060", "LCU-Hrs", productFamily="Load Balancer-Network"),
    ],
    "AmazonEKS": [
        listed("EUC1-AmazonEKS-Hours:perCluster", "0.10", tiertype="HAStandard",
               operation="CreateOperation"),
        listed("EUC1-AmazonEKS-Local-Outposts-Hours:perCluster", "0.30",
               tiertype="HAStandard", operation="CreateOperation"),
        listed("EUC1-AmazonEKS-Hours:extendedSupport", "0.50", tiertype="HAExtended",
               operation="ExtendedSupport"),
    ],
}


class Aws:
    """The CLI calls aws.py makes, answered from CATALOG and what is set here."""

    def __init__(self, spot="0.0400", volumes=None, cluster=None, status="STANDARD_SUPPORT"):
        self.spot = spot
        self.volumes = {"vol-0aaa": "gp3"} if volumes is None else volumes
        self.cluster = {"version": "1.31"} if cluster is None else cluster
        self.status = status
        self.asked: list[list[str]] = []

    def sh_json(self, cmd, timeout=60):
        self.asked.append(cmd)
        if cmd[:3] == ["aws", "pricing", "get-products"]:
            return {"PriceList": self.products(cmd)}
        if cmd[:3] == ["aws", "ec2", "describe-spot-price-history"]:
            return {"SpotPriceHistory": [{"SpotPrice": self.spot}] if self.spot else []}
        if cmd[:3] == ["aws", "ec2", "describe-volumes"]:
            wanted = cmd[cmd.index("--filters") + 1].split("Values=")[1].split(",")
            return {"Volumes": [{"VolumeId": v, "VolumeType": t}
                                for v, t in self.volumes.items() if v in wanted]}
        if cmd[:3] == ["aws", "eks", "describe-cluster"]:
            return {"cluster": self.cluster}
        if cmd[:3] == ["aws", "eks", "describe-cluster-versions"]:
            return {"clusterVersions": [{"clusterVersion": self.cluster.get("version"),
                                         "versionStatus": self.status}]}
        raise AssertionError(f"unexpected aws: {cmd}")

    @staticmethod
    def products(cmd: list[str]) -> list[str]:
        service = cmd[cmd.index("--service-code") + 1]
        terms = dict(term.split(",Field=")[1].split(",Value=")
                     for term in cmd if term.startswith("Type=TERM_MATCH"))
        return [json.dumps({
            "product": {"attributes": {key: value for key, value in entry.items()
                                       if key not in ("unit", "usd")}},
            "terms": {"OnDemand": {"t": {"priceDimensions": {"d": {
                "unit": entry["unit"], "pricePerUnit": {"USD": entry["usd"]}}}}}}})
            for entry in CATALOG.get(service, [])
            if all(entry.get(field) == value for field, value in terms.items())]


@pytest.fixture(autouse=True)
def no_cached_rates():
    """aws.py caches per process; one test's rates must not answer the next's."""
    for cache in (aws._ondemand_cache, aws._spot_cache, aws._listed_cache):
        cache.clear()
    yield


def checked(prometheus: Prometheus, fake: Aws | None = None, lines=None,
            within: float = 0.01, cluster: str | None = "demo"):
    plan = {"within": within, "lines": ALL_LINES if lines is None else lines,
            "eks_cluster": cluster}
    with patch("report_kit.shell.http_json", prometheus.http_json), \
            patch("report_kit.shell.sh_json", (fake or Aws()).sh_json):
        return price_check.check_prices("http://prom", WINDOW, plan)


class TestWhatOpenCostPublished:
    def test_the_lines_a_register_reads_are_named_by_their_metrics(self):
        queries = ['sum(max by (node) (node_total_hourly_cost) * on (node) group_left () '
                   'kube_node_labels{label_karpenter_sh_nodepool="apps"}) or vector(0)',
                   "sum(kubecost_load_balancer_cost)", "sum(rate(requests_total[1m]))"]
        assert opencost.lines_read(queries) == (opencost.NODES, opencost.LOAD_BALANCERS)
        assert opencost.lines_read(["sum(container_cpu_allocation * on (node) "
                                    "group_left () node_cpu_hourly_cost)"]) == (opencost.NODES,)
        assert opencost.lines_read(["sum(up)"]) == ()

    def test_a_price_is_kept_where_it_starts_and_where_it_changes(self):
        prices = opencost.price_changes(opencost.NODES, {"node": "n1"},
                                        held("0.04", "0.04", "0.05", "0.05"))
        assert [(p.hourly, p.since.minute) for p in prices] == [(0.04, 0), (0.05, 2)]
        assert {p.item for p in prices} == {"n1"}

    def test_a_node_is_spot_when_opencost_says_so_at_any_instant(self):
        prometheus = Prometheus(nodes=[node("n1", "0.04"), node("n2", "0.10")], spot=["n1"])
        with patch("report_kit.shell.http_json", prometheus.http_json):
            prices = opencost.published_prices("http://prom", WINDOW, [opencost.NODES])
        assert {p.item: p.labels["spot"] for p in prices} == {"n1": True, "n2": False}


class TestNodes:
    def test_an_on_demand_node_at_the_listed_rate_is_clean(self):
        check = checked(Prometheus(nodes=[node("n1", "0.1000")]), lines=[opencost.NODES])
        assert check.doubts == []
        assert [(one.price.item, one.aws) for one in check.checked] == [("n1", 0.1)]

    def test_a_spot_node_priced_at_the_on_demand_rate_is_doubted(self):
        # What OpenCost publishes for a spot node with no data feed and no
        # price history: the on-demand rate.
        check = checked(Prometheus(nodes=[node("n1", "0.1000")], spot=["n1"]),
                        lines=[opencost.NODES])
        assert len(check.doubts) == 1
        assert "node n1 at $0.1/h" in check.doubts[0]
        assert "AWS publishes $0.04/h — 150.0% apart" in check.doubts[0]

    def test_a_difference_inside_the_tolerance_is_not(self):
        check = checked(Prometheus(nodes=[node("n1", "0.1005")]), lines=[opencost.NODES])
        assert check.doubts == []

    def test_a_node_not_on_ec2_cannot_be_checked(self):
        check = checked(Prometheus(nodes=[node("n1", "0.03", provider="k3s://n1")]),
                        lines=[opencost.NODES])
        assert check.doubts == ["OpenCost's price for node n1 could not be checked "
                                "against AWS — not an EC2 instance (provider_id 'k3s://n1')"]

    def test_a_node_opencost_never_priced_is_doubted(self):
        check = checked(Prometheus(nodes=[node("n1", "0.1000")], unpriced=["n2"]),
                        lines=[opencost.NODES])
        assert check.doubts == ["node n2 ran in the window with no price from OpenCost — "
                                "a sum over node prices is short by it"]

    def test_spot_history_is_asked_in_the_zones_own_region(self):
        fake = Aws()
        checked(Prometheus(nodes=[node("n1", "0.04")], spot=["n1"]), fake,
                lines=[opencost.NODES])
        spot = next(cmd for cmd in fake.asked if "describe-spot-price-history" in cmd)
        assert spot[spot.index("--region") + 1] == REGION
        assert spot[spot.index("--availability-zone") + 1] == ZONE


def volume(name: str, price: str, provider: str = "vol-0aaa") -> dict:
    return {"metric": {"persistentvolume": name, "provider_id": provider},
            "values": held(price)}


class TestVolumes:
    def test_a_gp3_volume_is_held_against_the_gb_month_rate_over_730_hours(self):
        check = checked(Prometheus(nodes=[node("n1", "0.1000")],
                                   volumes=[volume("pv-1", str(0.095 / 730))]),
                        lines=[opencost.VOLUMES])
        assert check.doubts == []
        assert check.checked[0].aws == pytest.approx(0.095 / 730)

    def test_a_volume_ec2_no_longer_describes_cannot_be_checked(self):
        check = checked(Prometheus(volumes=[volume("pv-1", "0.0001", "vol-0gone")]),
                        Aws(volumes={}), lines=[opencost.VOLUMES])
        assert check.doubts == ["OpenCost's price for volume pv-1 could not be checked "
                                "against AWS — EC2 no longer describes vol-0gone"]

    def test_without_one_region_nothing_regional_is_checked(self):
        check = checked(Prometheus(volumes=[volume("pv-1", "0.0001")], regions=()),
                        lines=[opencost.VOLUMES])
        assert "no single region named by the node prices" in check.doubts[0]


class TestLoadBalancersAndControlPlane:
    def test_opencosts_fallback_load_balancer_price_is_doubted(self):
        balancer = {"metric": {"namespace": "shop", "service_name": "edge"},
                    "values": held("0.025")}
        check = checked(Prometheus(balancers=[balancer]), lines=[opencost.LOAD_BALANCERS])
        assert len(check.doubts) == 1
        assert "load balancer shop/edge at $0.025/h" in check.doubts[0]
        assert "AWS publishes $0.027/h" in check.doubts[0]

    def plane(self, price: str) -> list:
        return [{"metric": {"provisioner_name": "EKS"}, "values": held(price)}]

    def test_a_cluster_opencost_does_not_charge_for_is_doubted(self):
        # A cluster with no managed node group: OpenCost publishes no fee.
        check = checked(Prometheus(plane=self.plane("0")), lines=[opencost.CONTROL_PLANE])
        assert "control plane EKS at $0/h" in check.doubts[0]
        assert "AWS publishes $0.1/h" in check.doubts[0]

    def test_extended_support_is_part_of_the_fee(self):
        check = checked(Prometheus(plane=self.plane("0.10")), Aws(status="EXTENDED_SUPPORT"),
                        lines=[opencost.CONTROL_PLANE])
        assert check.checked[0].aws == pytest.approx(0.60)
        assert len(check.doubts) == 1

    def test_the_standard_fee_matches(self):
        check = checked(Prometheus(plane=self.plane("0.10")), lines=[opencost.CONTROL_PLANE])
        assert check.doubts == []

    @pytest.mark.parametrize("fake, cluster, problem", [
        (Aws(), None, "env.yaml names no eks_cluster"),
        (Aws(cluster={"version": "1.31", "controlPlaneScalingConfig": {"tier": "tier-xl"}}),
         "demo", "provisioned control-plane tier 'tier-xl' is not priced by this check"),
    ])
    def test_a_fee_it_cannot_work_out_is_doubted(self, fake, cluster, problem):
        check = checked(Prometheus(plane=self.plane("0.10")), fake,
                        lines=[opencost.CONTROL_PLANE], cluster=cluster)
        assert check.doubts == [f"OpenCost's price for control plane EKS could not be "
                                f"checked against AWS — {problem}"]


class TestWhatOpenCostDidNotPublish:
    def test_a_line_the_register_reads_with_no_price_at_all_is_doubted(self):
        check = checked(Prometheus(nodes=[node("n1", "0.1000")]),
                        lines=[opencost.NODES, opencost.LOAD_BALANCERS])
        assert check.doubts == ["the register reads a load balancer price, and OpenCost "
                                "published none during the window"]

    def test_prometheus_failing_is_a_doubt_not_an_exception(self):
        def down(method, url, body=None, timeout=30):
            raise RuntimeError("connection refused")
        with patch("report_kit.shell.http_json", down):
            check = price_check.check_prices("http://prom", WINDOW, {
                "within": 0.01, "lines": [opencost.NODES], "eks_cluster": None})
        assert check.doubts == ["OpenCost's prices could not be read — connection refused"]
        assert price_check.recorded(check)["unread"] == "connection refused"


class TestTheListedRates:
    def test_a_usage_type_is_matched_without_its_region_prefix(self):
        with patch("report_kit.shell.sh_json", Aws().sh_json):
            assert aws.nlb_hourly(REGION) == pytest.approx(0.027)
            assert aws.ebs_gb_month("gp3", REGION) == pytest.approx(0.095)
            assert aws.eks_cluster_hourly(REGION) == pytest.approx(0.10)
            assert aws.eks_extended_support_hourly(REGION) == pytest.approx(0.50)

    @pytest.mark.parametrize("zone, region", [("eu-central-1a", "eu-central-1"),
                                              ("us-east-1-bos-1a", "us-east-1"),
                                              ("us-gov-west-1b", "us-gov-west-1")])
    def test_a_zone_names_its_region(self, zone, region):
        assert aws.region_of_zone(zone) == region


REGISTER_TEXT = """\
metrics:
  M1:
    what: price of the nodes in the pool
    promql: sum(max by (node) (node_total_hourly_cost)) or vector(0)
    status: unconfirmed
  D2:
    what: mean node price over the window
    series: {ref: M1, reduce: mean}
    status: active
"""
REGISTER = parse_register(REGISTER_TEXT, Path("x/metrics.yaml"))


class TestTheExecutionAsksForIt:
    def test_the_tolerance_is_read(self):
        execution = parse_execution("prices_match_aws: {within: 0.02}\n",
                                    Path("x/execution.yaml"), REGISTER)
        assert execution.prices_match_aws == PriceMatch(0.02)

    def test_without_the_section_nothing_is_checked(self):
        execution = parse_execution("", Path("x/execution.yaml"), REGISTER)
        assert execution.prices_match_aws is None
        assert price_check.plan_of(None, ["node_total_hourly_cost"], "demo") is None

    @pytest.mark.parametrize("text, message", [
        ("prices_match_aws: {within: 0}", "between 0 and 1"),
        ("prices_match_aws: {within: 5}", "between 0 and 1"),
        ("prices_match_aws: {within: '1%'}", "between 0 and 1"),
        ("prices_match_aws: {tolerance: 0.01}", "unknown key 'tolerance'"),
        ("prices_match_aws: 0.01", "must be a mapping"),
    ])
    def test_a_tolerance_that_says_nothing_is_refused(self, text, message):
        with pytest.raises(ExecutionError, match=message):
            parse_execution(text, Path("x/execution.yaml"), REGISTER)

    def test_a_register_that_reads_no_opencost_price_has_nothing_to_check(self):
        register = parse_register("metrics:\n  M1: {what: up, promql: sum(up), "
                                  "status: unconfirmed}\n", Path("x/metrics.yaml"))
        with pytest.raises(ExecutionError, match="reads a price OpenCost publishes"):
            parse_execution("prices_match_aws: {within: 0.01}\n",
                            Path("x/execution.yaml"), register)

    def test_the_plan_names_the_lines_and_the_cluster(self):
        assert price_check.plan_of(0.01, ["sum(pv_hourly_cost)"], "demo") == {
            "within": 0.01, "lines": [opencost.VOLUMES], "eks_cluster": "demo"}


RECORD = {
    "run": "r24",
    "profile": "api",
    "settings": {"rate": "24"},
    "window": {"start": "2026-01-02T10:00:00Z", "end": "2026-01-02T10:10:00Z",
               "seconds": 600.0},
    "load": {"exit": 0, "window": None},
    "events": {"load_started": START, "load_finished": START + 300,
               "window_closed": START + 600},
    "observations": {"peaks": {}, "ceilings_reached": []},
    "doubts": [],
    "plan": {"step": "15s", "guards_at": "load_end"},
    "queries": {"M1": "sum(max by (node) (node_total_hourly_cost)) or vector(0)"},
    "guards": [],
    "commit": "a" * 40,
}


class ExportAndPrices(Prometheus):
    """The export's own range query answered beside the price check's."""

    def http_json(self, method, url, body=None, timeout=30):
        query = parse_qs(urlparse(url).query)["query"][0]
        if query == RECORD["queries"]["M1"]:
            return {"status": "success", "data": {"result": [
                {"metric": {}, "values": held("0.1", "0.1")}]}}
        return super().http_json(method, url, body, timeout)


def finished(tmp_path: Path, prometheus: Prometheus, record: dict) -> tuple[int, dict, str]:
    data = tmp_path / "data"
    data.mkdir()
    path = data / "r24.point.json"
    path.write_text(json.dumps(record))
    with patch("report_kit.shell.http_json", prometheus.http_json), \
            patch("report_kit.shell.sh_json", Aws().sh_json), \
            contextlib.redirect_stdout(io.StringIO()):
        code = finish.finish_point(path, "http://prom", REGISTER)
    return (code, json.loads(path.read_text()),
            path.with_name("r24.point.md").read_text())


class TestTheRecordCarriesIt:
    PLAN = {"within": 0.01, "lines": [opencost.NODES], "eks_cluster": None}

    def test_a_clean_check_is_the_price_basis_of_the_window(self, tmp_path):
        prometheus = ExportAndPrices(nodes=[node("n1", "0.1000")])
        code, record, block = finished(tmp_path, prometheus,
                                       {**RECORD, "price_check": self.PLAN})
        assert code == EXIT_CLEAN
        assert record["prices"]["checked"] == [
            {"line": "nodes", "item": "n1", "opencost": 0.1, "aws": 0.1,
             "since": "2026-01-02T10:00:00Z", "problem": ""}]
        assert (record["prices"]["silent"], record["prices"]["unread"]) == ([], "")
        assert "| prices | 1 checked against AWS within 1.0%, clean |" in block

    def test_a_price_in_doubt_makes_the_point_suspect(self, tmp_path):
        prometheus = ExportAndPrices(nodes=[node("n1", "0.1000")], spot=["n1"])
        code, record, block = finished(tmp_path, prometheus,
                                       {**RECORD, "price_check": self.PLAN})
        assert code == EXIT_SUSPECT
        assert record["doubts"] == []
        assert len(record["prices"]["doubts"]) == 1
        assert "1 in doubt" in block
        assert validity_problems(record) == [f"price doubts: {record['prices']['doubts'][0]}"]

    def test_a_record_without_a_plan_is_not_checked(self, tmp_path):
        code, record, block = finished(tmp_path, ExportAndPrices(), RECORD)
        assert code == EXIT_CLEAN
        assert record["prices"] is None
        assert "| prices |" not in block


class TestPreflightNamesTheCluster:
    """The control-plane fee is checked against a named cluster; finding it
    unnamed after the window closed would cost the point."""

    def opened(self, tmp_path: Path, env: str):
        (tmp_path / "metrics.yaml").write_text(
            "metrics:\n  M1: {what: fee, promql: max(kubecost_cluster_management_cost), "
            "status: unconfirmed}\n")
        (tmp_path / "execution.yaml").write_text("prices_match_aws: {within: 0.01}\n")
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "env.yaml").write_text("namespace: app\nprometheus: {url: 'http://prom'}\n"
                                          + env)
        return points.open_point(scripts, "api", PointPlan(settings=(Setting("rate"),)),
                                 "", ["--run", "r1", "--rate", "1"])

    @pytest.mark.parametrize("env, failures", [("", 1), ("eks_cluster: demo\n", 0)])
    def test_a_checked_fee_needs_eks_cluster(self, tmp_path, env, failures):
        pre = Preflight("preflight")
        with contextlib.redirect_stdout(io.StringIO()):
            points.check_price_inputs(self.opened(tmp_path, env), pre)
        assert len(pre.failures) == failures
