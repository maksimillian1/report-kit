#!/usr/bin/env python3
"""selftest.py — run both runner templates end to end against a faked cluster.

    report-kit selftest

No pytest, no cluster, no AWS. It patches the three functions everything
bottoms out in (shell.sh / sh_json / http_json) and drives a full point:
preflight, load, the window closing, export, guards, the point record.

Two things it is for. It proves the seam the docs claim — if this file needs
anything beyond those three patches to fake a cluster, then something in the
package is reaching around them. And it is the worked example to copy when
testing a runner you wrote: the fakes below are 60 lines, and they are all
the fixture machinery there is.

The runners it drives are loaded straight out of `templates/runners/` — the
same files `report-kit new-point` copies into a project. Testing a stand-in
would prove nothing about what people actually run.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from importlib.resources import as_file, files
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from report_kit import shell  # (patched by name below)
from report_kit.tools import node_cost


def load_runner(name: str):
    """Import a runner out of templates/runners/ — package data, not a module.

    Bytecode writing is off for the duration: templates/ is shipped verbatim,
    and a __pycache__ left behind here would be packaged into the wheel and
    handed to every project."""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        with as_file(files("report_kit") / "templates" / "runners" / f"{name}.py") as path:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


IMAGE = "ghcr.io/example/app@sha256:" + "0" * 64


class FakeCluster:
    """Answers kubectl/aws/HTTP the way a cluster would while a point runs.

    Idle until the load starts, busy for `busy_polls` after that, then back
    at the floor so the window can actually close. "Load started" is not a
    flag the test sets: the runner launches a real generator process, and
    that process touches `marker`. So the fake reacts to the same causality
    the real system does, and the real proc.run_logged / proc.Background code
    is exercised rather than stubbed."""

    def __init__(self, marker: Path, busy_polls: int = 2):
        self.marker = marker
        self.busy_polls = busy_polls
        self.polls = 0
        self.polls_at_start: int | None = None

    @property
    def busy(self) -> bool:
        if not self.marker.exists():
            return False            # preflight: nothing has been asked of it yet
        # Counted from the poll the load started on, not from zero: preflight
        # reads the cluster several times before the generator is even
        # launched, and against a fixed budget those reads spent it. The busy
        # phase then never opened and both runners watched a system that was
        # idle from the first poll — the window closed immediately and every
        # assertion below still passed.
        if self.polls_at_start is None:
            self.polls_at_start = self.polls
        return self.polls - self.polls_at_start < self.busy_polls

    def sh(self, cmd, timeout=60):
        if cmd[:2] == ["git", "rev-parse"]:
            return "a" * 40 + "\n"
        if cmd[:2] == ["git", "status"]:
            return ""
        if cmd[:3] == ["aws", "sqs", "purge-queue"]:
            return ""
        if cmd[:3] == ["aws", "s3", "rm"]:
            return "delete: s3://b/one\n"
        raise AssertionError(f"unexpected sh: {cmd}")

    def sh_json(self, cmd, timeout=60):
        if cmd[:3] == ["aws", "sqs", "get-queue-attributes"]:
            return {"Attributes": {
                "ApproximateNumberOfMessages": "500" if self.busy else "0",
                "ApproximateNumberOfMessagesNotVisible": "0"}}
        if cmd[:3] == ["kubectl", "get", "nodes"]:
            self.polls += 1
            if not self.busy:
                return {"items": []}
            return {"items": [{"metadata": {
                "name": "node-1",
                "labels": {"node.kubernetes.io/instance-type": "m5.large"}}}]}
        if cmd[:2] == ["kubectl", "get"] and "events" in cmd:
            return {"items": []}
        if "pods" in cmd:
            if not self.busy:
                return {"items": []}
            return {"items": [{"metadata": {"name": "worker-1"},
                               "spec": {"nodeName": "node-1"}}]}
        if "deployment" in cmd:
            # One command shape serves two callers: deployment_replicas reads
            # status, frozen_images reads the pod template. A real cluster
            # returns both in one object, so the fake does too.
            self.polls += 1
            return {"status": {"replicas": 4 if self.busy else 1},
                    "spec": {"template": {"spec": {"containers": [
                        {"image": IMAGE}]}}}}
        raise AssertionError(f"unexpected sh_json: {cmd}")

    def http_json(self, method, url, body=None, timeout=30):
        query = parse_qs(urlparse(url).query).get("query", [""])[0]
        if "/api/v1/query_range" in url:
            return {"status": "success", "data": {"result": [
                {"metric": {"job": "app", "pod": "app-1"},
                 "values": [[1757000000, "1"], [1757000015, "2"]]}]}}
        if "/api/v1/query" in url:
            if query.strip() == "up == 0":      # nothing is down
                return {"status": "success", "data": {"result": []}}
            return {"status": "success", "data": {"result": [
                {"metric": {}, "value": [1757000000, "1"]}]}}
        raise AssertionError(f"unexpected http: {url}")


def write_inputs(root: Path, profile: str) -> None:
    (root / "series.txt").write_text("M1|sum(rate(requests_total[1m]))\n")
    (root / "guards.txt").write_text("G1|max 5|sum(errors_total)\n")
    (root / "image-freeze.json").write_text(json.dumps(
        {"deployment/api": [IMAGE]} if profile == "api" else
        {"deployment/worker": [IMAGE], "deployment/embeddings": [IMAGE]},
        indent=2) + "\n")


def env_yaml(profile: str, marker: Path) -> str:
    """The generator/producer is a real process that touches the marker — see
    FakeCluster. poll_seconds 0 keeps the test fast; the hold logic is
    exercised by the poll count, not by wall-clock time."""
    touch = f"open({str(marker)!r}, 'w').close()"
    common = ("namespace: app\npoll_seconds: 0.05\nmax_wait_seconds: 20\n"
              "prometheus:\n  url: http://localhost:9090\n")
    if profile == "api":
        return common + f'generator:\n  command: ["python3", "-c", "{touch}"]\n'
    return (common
            + f'producer:\n  command: ["python3", "-c", "{touch}"]\n'
            + "sqs:\n  work: https://sqs.example/q\n  retry: https://sqs.example/r\n"
            + "nodepool_workers: pool=workers\nworker_selector: app=worker\n")


def run_profile(profile: str) -> int:
    root = Path(tempfile.mkdtemp(prefix=f"smoke-{profile}-"))
    try:
        marker = root / "load-started"
        write_inputs(root, profile)
        (root / "env.yaml").write_text(env_yaml(profile, marker))
        fake = FakeCluster(marker)

        runner = load_runner("api_point" if profile == "api" else "jobs_point")
        argv = ["x", "--run", f"smoke-{profile}", "--env", str(root / "env.yaml"),
                "--series", str(root / "series.txt"),
                "--guards", str(root / "guards.txt"),
                "--freeze-file", str(root / "image-freeze.json"),
                "--out-dir", str(root / "data"), "--no-port-forward"]
        argv += ["--rate", "200"] if profile == "api" else ["--n", "8", "--count", "100"]

        # The tuning is the project's, not the flow's: a 90s hold would make
        # this test take 90s to prove nothing extra.
        with patch("report_kit.shell.sh", fake.sh), \
             patch("report_kit.shell.sh_json", fake.sh_json), \
             patch("report_kit.shell.http_json", fake.http_json), \
             patch.object(runner, "HOLD_SECONDS", 0.2), \
             patch.object(sys, "argv", argv):
            code = runner.main()

        record = json.loads((root / "data" / f"smoke-{profile}.point.json").read_text())
        # > 0, not >= 0. A runner that closes its window at the very first
        # poll records a zero-length window, and every other assertion here
        # passes anyway — which is exactly how jobs_point.py shipped able to
        # measure nothing and report it clean.
        assert record["window"]["seconds"] > 0, record["window"]
        assert record["export"]["series"] == 1, record["export"]
        assert (root / "data" / f"smoke-{profile}.point.md").is_file()
        assert (root / "data" / f"smoke-{profile}.jsonl").is_file()
        print(f"\n[  ok  ] {profile}: exit {code}, window "
              f"{record['window']['seconds']}s, point files written")
        return 0
    except SystemExit as e:
        print(f"\n[ FAIL ] {profile}: runner exited early with code {e.code}")
        return 1
    except Exception as e:
        print(f"\n[ FAIL ] {profile}: {type(e).__name__}: {e}")
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_node_cost() -> int:
    """The cost pipeline has no local equivalent — a laptop cluster has neither
    Karpenter nor an AWS bill — so this is the only thing that exercises it.
    Same three patches as the runners: if it needed more, the seam would be
    leaking."""
    from datetime import datetime, timezone
    start = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc).timestamp()

    def http_json(method, url, body=None, timeout=30):
        if "kube_node_labels" in url:
            return {"status": "success", "data": {"result": [
                {"metric": {"node": "node-a",
                            "label_karpenter_sh_nodepool": "compute"},
                 "values": [[start, "1"], [start + 900, "1"]]}]}}
        if "kube_node_info" in url:
            return {"status": "success", "data": {"result": [
                {"metric": {"node": "node-a",
                            "provider_id": "aws:///eu-central-1a/i-aaa"},
                 "values": [[start, "1"]]}]}}
        raise AssertionError(f"unexpected http: {url}")

    def sh_json(cmd, timeout=60):
        if cmd[:3] == ["aws", "ec2", "describe-instances"]:
            return {"Reservations": [{"Instances": [
                {"InstanceId": "i-aaa", "InstanceType": "c6i.large",
                 "Placement": {"AvailabilityZone": "eu-central-1a"}}]}]}
        if cmd[:3] == ["aws", "pricing", "get-products"]:
            return {"PriceList": ['{"terms":{"OnDemand":{"t":{"priceDimensions":'
                                  '{"d":{"pricePerUnit":{"USD":"0.0970"}}}}}}}']}
        raise AssertionError(f"unexpected aws: {cmd}")

    try:
        argv = ["x", "--nodepool", "compute", "--prom-url", "http://p",
                "--start", "2026-01-02T10:00:00Z", "--end", "2026-01-02T10:30:00Z"]
        with patch("report_kit.shell.http_json", http_json), \
             patch("report_kit.shell.sh_json", sh_json), \
             patch.object(sys, "argv", argv):
            code = node_cost.main()
        assert code == 0, f"exit {code}"
        print("\n[  ok  ] node_cost: 15 min of a c6i.large priced end to end")
        return 0
    except SystemExit as e:
        print(f"\n[ FAIL ] node_cost: exited early with code {e.code}")
        return 1
    except Exception as e:
        print(f"\n[ FAIL ] node_cost: {type(e).__name__}: {e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    failures = sum(run_profile(profile) for profile in ("api", "jobs"))
    failures += run_node_cost()
    print()
    print("smoke test: " + ("everything passed" if not failures
                            else f"{failures} case(s) FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
