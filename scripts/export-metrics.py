#!/usr/bin/env python3
"""
export-metrics.py — Minimalist Prometheus range query exporter.
Zero dependencies. Dumps queries from a text file to JSONL.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROM_URL = os.environ.get("PROM_URL", "http://localhost:9090").rstrip("/")
TIMEOUT = int(os.environ.get("PROM_TIMEOUT", "60"))

def query_prometheus(path: str, params: dict) -> dict:
    url = f"{PROM_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") != "success":
                raise RuntimeError(data.get("error", "Unknown Prometheus error"))
            return data.get("data", {})
    except Exception as e:
        raise RuntimeError(f"Request failed: {e}")

def load_queries(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        sys.exit(f"ERROR: Query file not found: {path}")

    queries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, query = map(str.strip, line.split("|", 1))
        queries.append((name, query))
    return queries

def main():
    p = argparse.ArgumentParser(description="Export Prometheus metrics to JSONL.")
    p.add_argument("--run", required=True, help="Run ID (e.g., e1-n08)")
    p.add_argument("--start", required=True, help="Start time (RFC3339)")
    p.add_argument("--end", required=True, help="End time (RFC3339)")
    p.add_argument("--step", default="15s", help="Resolution step (e.g., 15s)")
    p.add_argument("--queries", default="queries.txt", help="Path to queries file")
    p.add_argument("--out-dir", default="data", help="Output directory")
    args = p.parse_args()

    out_path = Path(args.out_dir) / f"{args.run}.jsonl"
    if out_path.exists():
        sys.exit(f"ERROR: {out_path} already exists. Avoid overwriting execution data.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    queries = load_queries(Path(args.queries))
    records = []

    print(f"-> Target: {PROM_URL}")
    print(f"-> Window: {args.start} to {args.end} (step: {args.step})")

    for name, query in queries:
        try:
            data = query_prometheus("/api/v1/query_range", {
                "query": query, "start": args.start, "end": args.end, "step": args.step
            })
            result = data.get("result", [])
            points = sum(len(series.get("values", [])) for series in result)

            if not points:
                print(f" [WARN] {name}: NO DATA (Instrumentation gap or idle metric)")
                continue

            print(f" [OK]   {name}: {len(result)} series, {points} points")
            records.append({
                "run": args.run,
                "metric": name,
                "query": query,
                "start": args.start,
                "end": args.end,
                "step": args.step,
                "result": result
            })
        except Exception as e:
            print(f" [FAIL] {name}: {e}")

    with out_path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    print(f"-> Wrote {len(records)}/{len(queries)} successful metrics to {out_path}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
