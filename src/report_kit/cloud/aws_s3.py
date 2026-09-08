from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import boto3
from botocore.exceptions import ClientError

# Split from aws.py because this is the one module needing the boto3 SDK
# installed — everything in aws.py needs nothing but the `aws` CLI on PATH,
# and importing it shouldn't drag a pip dependency in behind it.


def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise


def upload_dir(bucket: str, src_dir: Path, prefix: str = "", *,
               s3=None, workers: int = 16, skip_existing: bool = True,
               content_type: str | Callable[[Path], str] = "application/octet-stream",
               transfer_config=None,
               on_progress: Callable[[int], None] | None = None,
               on_file: Callable[[Path, str], None] | None = None,
               ) -> tuple[list[str], list[str]]:
    """Upload every file under `src_dir` to `s3://bucket/prefix/<relative path>`,
    `workers` at a time. Returns (uploaded_keys, skipped_keys).

    The concurrency, the already-there check and the key derivation are the
    parts worth not rewriting per project; everything opinionated is a
    parameter:

      s3               an existing boto3 client, or None to build a default one
      skip_existing    HEAD each key first and skip what's already uploaded —
                       this is what makes a re-run after a partial upload cheap
      content_type     a fixed string, or a callable taking the local path
      transfer_config  a boto3.s3.transfer.TransferConfig; chunk-size and
                       concurrency trade-offs are call-site-specific
      on_progress      called with each chunk's byte count as it goes out
                       (pass a tqdm bar's .update; no progress library is
                       imported here)
      on_file          called with (path, key) as each file completes

    Raises on the first upload that fails — a partial corpus is worse than a
    loud stop, and `skip_existing` makes the retry cheap.
    """
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise RuntimeError(f"not a directory: {src_dir}")
    s3 = s3 or boto3.client("s3")
    prefix = prefix.strip("/")

    paths = sorted(p for p in src_dir.rglob("*") if p.is_file())
    keys = {p: "/".join(filter(None, (prefix, p.relative_to(src_dir).as_posix())))
            for p in paths}

    uploaded: list[str] = []
    skipped: list[str] = []
    todo = list(paths)
    if skip_existing:
        todo = []
        for p in paths:
            if object_exists(s3, bucket, keys[p]):
                skipped.append(keys[p])
            else:
                todo.append(p)
    if not todo:
        return uploaded, skipped

    def _one(path: Path) -> str:
        key = keys[path]
        ctype = content_type(path) if callable(content_type) else content_type
        s3.upload_file(str(path), bucket, key, Config=transfer_config,
                        ExtraArgs={"ContentType": ctype}, Callback=on_progress)
        if on_file:
            on_file(path, key)
        return key

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, p): p for p in todo}
        for future in as_completed(futures):
            uploaded.append(future.result())  # re-raises the first failure

    return uploaded, skipped
