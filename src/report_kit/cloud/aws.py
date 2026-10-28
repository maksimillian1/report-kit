from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .. import shell
from ..clock import rfc3339


def sqs_depth(queue_url: str) -> int:
    """Visible plus in-flight. A queue with zero visible and thirty in-flight is
    not drained."""
    data = shell.sh_json([
        "aws", "sqs", "get-queue-attributes", "--queue-url", queue_url,
        "--attribute-names",
        "ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible",
        "--output", "json",
    ])
    attrs = data.get("Attributes", {})
    return (int(attrs.get("ApproximateNumberOfMessages", 0))
            + int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)))


def sqs_purge(queue_url: str, timeout: int = 30) -> bool:
    """True if purge was requested, False if one is already in flight (AWS
    allows one purge per queue per 60s and refuses a second). Purge is
    asynchronous on AWS's side regardless — depth doesn't read zero
    immediately, poll it separately (e.g. via poll.poll_until) rather than
    treating this call's return as "already empty"."""
    try:
        shell.sh(["aws", "sqs", "purge-queue", "--queue-url", queue_url], timeout=timeout)
        return True
    except RuntimeError as e:
        if "PurgeQueueInProgress" in str(e):
            return False
        raise


def s3_rm_recursive(bucket: str, prefix: str, timeout: int = 180) -> int:
    """Returns the number of objects removed (0 if the prefix was already
    empty)."""
    out = shell.sh(["aws", "s3", "rm", f"s3://{bucket}/{prefix}", "--recursive"],
                   timeout=timeout)
    return len([line for line in out.splitlines() if line.strip()])


def describe_instances(instance_ids: list[str], timeout: int = 30) -> dict[str, dict]:
    """instance-id -> the EC2 description, in one batched call.

    Works for instances that are already gone: EC2 keeps terminated instances
    describable for roughly an hour, which is what makes pricing a window after
    the fact possible at all. Beyond that they disappear and the caller is left
    with whatever the metrics themselves recorded."""
    ids = sorted({i for i in instance_ids if i})
    if not ids:
        return {}
    data = shell.sh_json(["aws", "ec2", "describe-instances",
                          "--instance-ids", *ids, "--output", "json"],
                         timeout=timeout)
    return {inst["InstanceId"]: inst
            for res in data.get("Reservations", [])
            for inst in res.get("Instances", [])}


# The AWS Pricing API is only served from us-east-1/ap-south-1 regardless of
# which region you're pricing — a fixed query endpoint, not the priced region.
PRICING_REGION_ENDPOINT = "us-east-1"

# The Pricing API filters on a human-readable "location", not a region code,
# and offers no endpoint to map between them. Only regions actually used are
# listed; add yours, or pass `location=` directly.
LOCATION_BY_REGION = {
    "eu-central-1": "EU (Frankfurt)",
    "eu-west-1": "EU (Ireland)",
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-2": "US West (Oregon)",
}

_ondemand_cache: dict[tuple[str, str], float | None] = {}


def location_of(region: str) -> str:
    """An unmapped region raises rather than returning None: that is a fixable
    lookup-table gap, not a fact about the price, and None reads downstream
    as "unpriceable" and hides the real cause."""
    location = LOCATION_BY_REGION.get(region)
    if location is None:
        raise ValueError(
            f"no Pricing API location known for region {region!r} — add it to "
            f"LOCATION_BY_REGION (have: {', '.join(sorted(LOCATION_BY_REGION))}) "
            f"or pass location= explicitly")
    return location


def ondemand_hourly(instance_type: str, region: str,
                    location: str | None = None) -> float | None:
    """USD/hour for Linux, shared tenancy. None means the API returned no
    price for this instance type. Cached per (type, location) in-process only."""
    location = location or location_of(region)
    key = (instance_type, location)
    if key in _ondemand_cache:
        return _ondemand_cache[key]

    cmd = [
        "aws", "pricing", "get-products",
        "--service-code", "AmazonEC2",
        "--region", PRICING_REGION_ENDPOINT,
        "--filters",
        f"Type=TERM_MATCH,Field=instanceType,Value={instance_type}",
        f"Type=TERM_MATCH,Field=location,Value={location}",
        "Type=TERM_MATCH,Field=operatingSystem,Value=Linux",
        "Type=TERM_MATCH,Field=tenancy,Value=Shared",
        "Type=TERM_MATCH,Field=preInstalledSw,Value=NA",
        "Type=TERM_MATCH,Field=capacitystatus,Value=Used",
        "--output", "json",
    ]
    try:
        data = shell.sh_json(cmd, timeout=30)
    except RuntimeError:
        _ondemand_cache[key] = None
        return None

    for price_list_entry in data.get("PriceList", []):
        product = json.loads(price_list_entry)
        terms = product.get("terms", {}).get("OnDemand", {})
        for term in terms.values():
            for dim in term.get("priceDimensions", {}).values():
                usd = dim.get("pricePerUnit", {}).get("USD")
                if usd:
                    rate = float(usd)
                    _ondemand_cache[key] = rate
                    return rate

    _ondemand_cache[key] = None
    return None


_spot_cache: dict[tuple[str, str], float | None] = {}


def spot_hourly(instance_type: str, az: str, at: datetime) -> float | None:
    """Most recent spot price at or before `at`. Cached per (type, az) —
    same in-process-only caveat as ondemand_hourly."""
    key = (instance_type, az)
    if key in _spot_cache:
        return _spot_cache[key]

    window_start = at - timedelta(hours=1)
    cmd = [
        "aws", "ec2", "describe-spot-price-history",
        "--region", region_of_zone(az),
        "--instance-types", instance_type,
        "--availability-zone", az,
        "--product-descriptions", "Linux/UNIX",
        "--start-time", rfc3339(window_start),
        "--end-time", rfc3339(at + timedelta(minutes=1)),
        "--output", "json",
    ]
    try:
        data = shell.sh_json(cmd, timeout=30)
    except RuntimeError:
        _spot_cache[key] = None
        return None

    history = data.get("SpotPriceHistory", [])
    if not history:
        _spot_cache[key] = None
        return None

    rate = float(history[0]["SpotPrice"])  # most recent ≤ end-time, API returns newest-first
    _spot_cache[key] = rate
    return rate


ZONE_REGION = re.compile(r"^([a-z]{2}(?:-gov)?-[a-z]+-\d+)")

# The Price List API prefixes every usage type with a region code (EUC1-,
# USE2-, EU-) except in us-east-1, where it has none.
USAGE_REGION_PREFIX = re.compile(r"^[A-Z]{2,4}\d*-")


def region_of_zone(az: str) -> str:
    """eu-central-1a and us-east-1-bos-1a alike name their region first."""
    found = ZONE_REGION.match(az)
    if not found:
        raise ValueError(f"{az!r} does not read as an availability zone")
    return found.group(1)


@dataclass(frozen=True)
class ListedRate:
    """One on-demand price dimension of one Price List product."""

    usage_type: str
    unit: str
    usd: float


_listed_cache: dict[tuple, list[ListedRate]] = {}


def listed_rates(service_code: str, region: str, **terms: str) -> list[ListedRate]:
    """Every on-demand rate the Price List API holds for `service_code` in
    `region` whose attributes match `terms` exactly. A usage type comes back
    without its region prefix, so one name matches in every region."""
    key = (service_code, region, tuple(sorted(terms.items())))
    if key in _listed_cache:
        return _listed_cache[key]
    filters = [f"Type=TERM_MATCH,Field={field},Value={value}"
               for field, value in (("location", location_of(region)), *terms.items())]
    data = shell.sh_json(["aws", "pricing", "get-products",
                          "--service-code", service_code,
                          "--region", PRICING_REGION_ENDPOINT,
                          "--filters", *filters, "--output", "json"], timeout=30)
    rates = []
    for entry in data.get("PriceList", []):
        product = json.loads(entry)
        usage = USAGE_REGION_PREFIX.sub(
            "", product.get("product", {}).get("attributes", {}).get("usagetype", ""))
        for term in product.get("terms", {}).get("OnDemand", {}).values():
            for dim in term.get("priceDimensions", {}).values():
                usd = dim.get("pricePerUnit", {}).get("USD")
                if usd is not None:
                    rates.append(ListedRate(usage, dim.get("unit", ""), float(usd)))
    _listed_cache[key] = rates
    return rates


def listed_rate(rates: list[ListedRate], usage_type: str) -> float | None:
    found = {rate.usd for rate in rates if rate.usage_type == usage_type}
    return found.pop() if len(found) == 1 else None


def ebs_gb_month(volume_type: str, region: str) -> float | None:
    """USD per GB-month of storage for an EBS volume type. Provisioned IOPS
    and throughput are priced separately and are not in this number."""
    usage = "EBS:VolumeUsage" + ("" if volume_type == "standard" else f".{volume_type}")
    return listed_rate(listed_rates("AmazonEC2", region, productFamily="Storage",
                                    volumeApiName=volume_type), usage)


def nlb_hourly(region: str) -> float | None:
    """USD/hour a Network Load Balancer stands for, before LCUs."""
    return listed_rate(listed_rates("AWSELB", region,
                                    productFamily="Load Balancer-Network"),
                       "LoadBalancerUsage")


def eks_cluster_hourly(region: str) -> float | None:
    """USD/hour for one EKS control plane in standard support."""
    return listed_rate(listed_rates("AmazonEKS", region, tiertype="HAStandard"),
                       "AmazonEKS-Hours:perCluster")


def eks_extended_support_hourly(region: str) -> float | None:
    """USD/hour added to the control plane while its version is in extended
    support."""
    return listed_rate(listed_rates("AmazonEKS", region, operation="ExtendedSupport"),
                       "AmazonEKS-Hours:extendedSupport")


def describe_volumes(volume_ids: list[str], region: str,
                     timeout: int = 30) -> dict[str, dict]:
    """volume-id -> the EC2 description. A filter rather than --volume-ids,
    which fails the whole call when one volume is already gone."""
    ids = sorted({i for i in volume_ids if i})
    if not ids:
        return {}
    data = shell.sh_json(["aws", "ec2", "describe-volumes", "--region", region,
                          "--filters", f"Name=volume-id,Values={','.join(ids)}",
                          "--output", "json"], timeout=timeout)
    return {volume["VolumeId"]: volume for volume in data.get("Volumes", [])}


def describe_cluster(name: str, region: str, timeout: int = 30) -> dict:
    return shell.sh_json(["aws", "eks", "describe-cluster", "--name", name,
                          "--region", region, "--output", "json"],
                         timeout=timeout).get("cluster", {})


def cluster_version_status(version: str, region: str, timeout: int = 30) -> str | None:
    """STANDARD_SUPPORT, EXTENDED_SUPPORT or UNSUPPORTED, as EKS says today."""
    data = shell.sh_json(["aws", "eks", "describe-cluster-versions",
                          "--cluster-versions", version, "--region", region,
                          "--output", "json"], timeout=timeout)
    for entry in data.get("clusterVersions", []):
        if entry.get("clusterVersion") == version:
            return entry.get("versionStatus")
    return None
