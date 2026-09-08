from __future__ import annotations

from .. import shell


def points_count(qdrant_url: str, collection: str) -> int:
    """Exact count: the estimate on GET /collections lags indexing.

    A dropped collection (a reset step may delete rather than empty it) 404s
    here rather than counting 0 — tolerated as 0, since the two mean the same
    thing to a caller: nothing to invalidate a preflight over, and whatever
    writes to the collection recreates it on its first write."""
    try:
        body = shell.http_json(
            "POST", f"{qdrant_url}/collections/{collection}/points/count",
            {"exact": True})
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return 0
        raise
    return int(body.get("result", {}).get("count", 0) or 0)


def delete_collection_if_nonempty(qdrant_url: str, collection: str) -> bool:
    """True if the collection is empty afterward — it already was (points_count
    handles the 404-vs-empty case), or this just deleted it. False only if the
    delete call itself failed; an unreachable server instead raises, same as
    points_count(). Delete-only: recreating the collection with the right
    schema is left to whatever normally writes to it on its next write."""
    if points_count(qdrant_url, collection) == 0:
        return True
    try:
        shell.http_json("DELETE", f"{qdrant_url}/collections/{collection}")
        return True
    except RuntimeError:
        return False
