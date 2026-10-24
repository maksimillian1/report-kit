"""Every price OpenCost published during a point's window, held against what
AWS publishes for the same thing. A price further off than the execution
allows, or one that cannot be checked at all, is a reason to doubt the point:
every cost the register works out of it carries the error."""

from __future__ import annotations

from dataclasses import dataclass

from . import opencost
from .clock import rfc3339
from .cloud import aws
from .constants import BAD, OK
from .opencost import CONTROL_PLANE, LOAD_BALANCERS, NODES, VOLUMES, Price
from .window import Window

HOURS_PER_MONTH = 730       # methodology.md §8, and OpenCost's own divisor
EBS_VOLUME_PREFIX = "vol-"
AWS_PROVIDER_PREFIX = "aws:///"
STANDARD_TIERS = (None, "", "standard")
NOUN = {NODES: "node", VOLUMES: "volume", LOAD_BALANCERS: "load balancer",
        CONTROL_PLANE: "control plane"}


@dataclass(frozen=True)
class Checked:
    """One OpenCost price and AWS's for the same item; `problem` says why
    there is no AWS rate to hold it against."""

    price: Price
    aws: float | None
    problem: str = ""

    def apart(self) -> float:
        """How far OpenCost's price is from AWS's, as a share of AWS's."""
        if self.aws == 0:
            return 0.0 if self.price.hourly == 0 else float("inf")
        return abs(self.price.hourly - self.aws) / self.aws


@dataclass(frozen=True)
class PriceCheck:
    """`unpriced` are nodes OpenCost never priced, `silent` the lines the
    register reads that it published nothing for, `unread` why its prices
    could not be read at all."""

    within: float
    checked: tuple[Checked, ...] = ()
    unpriced: tuple[str, ...] = ()
    silent: tuple[str, ...] = ()
    unread: str = ""

    def differs(self, one: Checked) -> bool:
        return one.aws is not None and one.apart() > self.within

    @property
    def doubts(self) -> list[str]:
        if self.unread:
            return [f"OpenCost's prices could not be read — {self.unread}"]
        doubts = [f"the register reads a {NOUN[line]} price, and OpenCost published "
                  f"none during the window" for line in self.silent]
        doubts += [f"OpenCost's price for {named(one.price)} could not be checked "
                   f"against AWS — {one.problem}"
                   for one in self.checked if one.aws is None]
        doubts += [f"OpenCost priced {named(one.price)} at "
                   f"${one.price.hourly:.6g}/h from {rfc3339(one.price.since)}, AWS "
                   f"publishes ${one.aws:.6g}/h — {one.apart():.1%} apart, more than "
                   f"the {self.within:.1%} allowed"
                   for one in self.checked if self.differs(one)]
        doubts += [f"node {node} ran in the window with no price from OpenCost — "
                   f"a sum over node prices is short by it" for node in self.unpriced]
        return doubts


def named(price: Price) -> str:
    return f"{NOUN[price.line]} {price.item}"


def plan_of(within: float | None, queries, eks_cluster: str | None) -> dict | None:
    """What the check needs, written into the point record so that
    `report-kit point finish` can run it again on the record alone."""
    if within is None:
        return None
    return {"within": within, "lines": list(opencost.lines_read(queries)),
            "eks_cluster": eks_cluster}


def check_prices(prom_url: str, window: Window, plan: dict) -> PriceCheck:
    """Prometheus failing is a doubt rather than an exception: the export
    before it has already succeeded, and the record must still be written."""
    lines, within = tuple(plan["lines"]), float(plan["within"])
    try:
        prices = opencost.published_prices(prom_url, window, lines)
        region = cluster_region(prom_url, window, prices)
        unpriced = opencost.unpriced_nodes(prom_url, window) if NODES in lines else []
    except RuntimeError as exc:
        return PriceCheck(within, unread=str(exc))
    of = {line: [p for p in prices if p.line == line] for line in lines}
    checked = [*node_checks(of.get(NODES, [])),
               *volume_checks(of.get(VOLUMES, []), region),
               *load_balancer_checks(of.get(LOAD_BALANCERS, []), region),
               *control_plane_checks(of.get(CONTROL_PLANE, []),
                                     plan.get("eks_cluster"), region)]
    return PriceCheck(within, tuple(checked), tuple(unpriced),
                      tuple(line for line in lines if not of[line]))


def cluster_region(prom_url: str, window: Window, prices: list[Price]) -> str | None:
    """The one region the node prices name; None when they name none or several."""
    priced = {p.labels.get("region", "") for p in prices if p.line == NODES} - {""}
    found = priced or opencost.regions(prom_url, window)
    return found.pop() if len(found) == 1 else None


def asked(price: Price, rate) -> Checked:
    """AWS's rate for one price, the lookup's failure turned into the reason."""
    try:
        value = rate()
    except (RuntimeError, ValueError) as exc:
        return Checked(price, None, str(exc).splitlines()[0] if str(exc) else repr(exc))
    if value is None:
        return Checked(price, None, "AWS returned no rate for it")
    return Checked(price, value)


def node_checks(prices: list[Price]) -> list[Checked]:
    return [node_check(price) for price in prices]


def node_check(price: Price) -> Checked:
    provider = price.labels.get("provider_id", "")
    kind = price.labels.get("instance_type", "")
    if not provider.startswith(AWS_PROVIDER_PREFIX):
        return Checked(price, None, f"not an EC2 instance (provider_id {provider!r})")
    if not kind:
        return Checked(price, None, "OpenCost names no instance_type for it")
    zone = provider[len(AWS_PROVIDER_PREFIX):].split("/")[0]
    if price.labels.get("spot"):
        return asked(price, lambda: aws.spot_hourly(kind, zone, price.since))
    return asked(price, lambda: aws.ondemand_hourly(kind, aws.region_of_zone(zone)))


def volume_checks(prices: list[Price], region: str | None) -> list[Checked]:
    if not prices:
        return []
    if region is None:
        return [Checked(p, None, "no single region named by the node prices")
                for p in prices]
    ids = [p.labels.get("provider_id", "") for p in prices]
    try:
        described = aws.describe_volumes(
            [i for i in ids if i.startswith(EBS_VOLUME_PREFIX)], region)
    except RuntimeError as exc:
        return [Checked(p, None, f"describe-volumes failed: {exc}") for p in prices]
    return [volume_check(p, described, region) for p in prices]


def volume_check(price: Price, described: dict[str, dict], region: str) -> Checked:
    volume_id = price.labels.get("provider_id", "")
    if not volume_id.startswith(EBS_VOLUME_PREFIX):
        return Checked(price, None, f"not an EBS volume (provider_id {volume_id!r})")
    if volume_id not in described:
        return Checked(price, None, f"EC2 no longer describes {volume_id}")
    kind = described[volume_id].get("VolumeType", "")
    return asked(price, lambda: per_gib_hour(aws.ebs_gb_month(kind, region)))


def per_gib_hour(gb_month: float | None) -> float | None:
    return None if gb_month is None else gb_month / HOURS_PER_MONTH


def load_balancer_checks(prices: list[Price], region: str | None) -> list[Checked]:
    if region is None:
        return [Checked(p, None, "no single region named by the node prices")
                for p in prices]
    return [asked(p, lambda: aws.nlb_hourly(region)) for p in prices]


def control_plane_checks(prices: list[Price], cluster: str | None,
                         region: str | None) -> list[Checked]:
    if not prices:
        return []
    if not cluster or region is None:
        problem = ("env.yaml names no eks_cluster" if not cluster
                   else "no single region named by the node prices")
        return [Checked(p, None, problem) for p in prices]
    return [asked(p, lambda: control_plane_hourly(cluster, region)) for p in prices]


def control_plane_hourly(cluster: str, region: str) -> float | None:
    """The fee AWS charges for this cluster's control plane today: standard
    support, plus extended support while its version is in it."""
    described = aws.describe_cluster(cluster, region)
    tier = (described.get("controlPlaneScalingConfig") or {}).get("tier")
    if tier not in STANDARD_TIERS:
        raise ValueError(f"provisioned control-plane tier {tier!r} is not priced "
                         f"by this check")
    standard = aws.eks_cluster_hourly(region)
    status = aws.cluster_version_status(described.get("version", ""), region)
    if standard is None or status != "EXTENDED_SUPPORT":
        return standard
    extended = aws.eks_extended_support_hourly(region)
    return None if extended is None else standard + extended


def recorded(check: PriceCheck) -> dict:
    """The check as the point record keeps it: the price basis of the window."""
    return {"within": check.within,
            "checked": [{"line": one.price.line, "item": one.price.item,
                         "opencost": one.price.hourly, "aws": one.aws,
                         "since": rfc3339(one.price.since), "problem": one.problem}
                        for one in check.checked],
            "unpriced": list(check.unpriced), "silent": list(check.silent),
            "unread": check.unread, "doubts": check.doubts}


def print_check(check: PriceCheck) -> None:
    if check.unread:
        print(f"[{BAD}] prices — {check.unread}")
    for line in check.silent:
        print(f"[{BAD}] price of every {NOUN[line]} — none published by OpenCost")
    for one in check.checked:
        mark = OK if one.aws is not None and not check.differs(one) else BAD
        aws_side = f"${one.aws:.6g}/h" if one.aws is not None else one.problem
        print(f"[{mark}] price of {named(one.price)} "
              f"${one.price.hourly:.6g}/h · AWS {aws_side}")
    for node in check.unpriced:
        print(f"[{BAD}] price of node {node} — never published by OpenCost")
