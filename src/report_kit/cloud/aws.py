from __future__ import annotations

import json
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


def ondemand_hourly(instance_type: str, region: str,
                    location: str | None = None) -> float | None:
    """USD/hour for Linux, shared tenancy. None means the API returned no
    price for this instance type; an unmapped region raises instead, since
    that's a fixable lookup-table gap rather than a fact about the price —
    silently returning None there reads downstream as "unpriceable instance"
    and hides the real cause. Cached per (type, location) in-process only."""
    if location is None:
        location = LOCATION_BY_REGION.get(region)
        if location is None:
            raise ValueError(
                f"no Pricing API location known for region {region!r} — add it to "
                f"LOCATION_BY_REGION (have: {', '.join(sorted(LOCATION_BY_REGION))}) "
                f"or pass location= explicitly")

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
