#!/usr/bin/env bash
# scripts/export-metrics.sh
#
# Snapshot Prometheus range queries into docs/report/data/ before retention expires.
#
#   ./export-metrics.sh --run e1-n08 --start "2026-08-20T10:00:00Z" --end "2026-08-20T10:25:00Z"
#   ./export-metrics.sh --run smoke --last 10m --dry-run
#
# Requires: curl, jq. Prometheus reachable at $PROM_URL
#   kubectl -n monitoring port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090

set -euo pipefail

PROM_URL="${PROM_URL:-http://localhost:9090}"
QUERY_FILE="${QUERY_FILE:-$(dirname "$0")/queries.txt}"
OUT_DIR="${OUT_DIR:-docs/report/data}"
STEP="${STEP:-15s}"
RUN=""; START=""; END=""; DRY=0

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run)     RUN="$2"; shift 2 ;;
    --start)   START="$2"; shift 2 ;;
    --end)     END="$2"; shift 2 ;;
    --last)    END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
               START="$(date -u -d "-$2" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
                     || date -u -v "-$2" +%Y-%m-%dT%H:%M:%SZ)"
               shift 2 ;;
    --step)    STEP="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) die "unknown arg: $1" ;;
  esac
done

[[ -n "$RUN"   ]] || die "--run is required (e.g. e1-n08)"
[[ -n "$START" ]] || die "--start/--end or --last is required"
[[ -f "$QUERY_FILE" ]] || die "query file not found: $QUERY_FILE"

command -v jq >/dev/null || die "jq not installed"

# --- preflight: prove the export path works before trusting a run -------------
echo "→ Prometheus: $PROM_URL"
curl -sf "$PROM_URL/-/healthy" >/dev/null || die "Prometheus unreachable"

DOWN=$(curl -sfG "$PROM_URL/api/v1/query" --data-urlencode 'query=up == 0' \
       | jq -r '.data.result[] | "\(.metric.job)/\(.metric.instance)"')
if [[ -n "$DOWN" ]]; then
  echo "⚠  scrape targets DOWN — these components cannot be named as constraints:"
  echo "$DOWN" | sed 's/^/     /'
fi

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/${RUN}.jsonl"
[[ -f "$OUT" && $DRY -eq 0 ]] && die "$OUT already exists — pick another --run id"

echo "→ window: $START .. $END  step=$STEP"
echo "→ output: $OUT"

EMPTY=0; TOTAL=0
while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^# ]] && continue
  NAME="${line%%|*}"; QUERY="${line#*|}"
  TOTAL=$((TOTAL+1))

  RESP=$(curl -sfG "$PROM_URL/api/v1/query_range" \
    --data-urlencode "query=${QUERY}" \
    --data-urlencode "start=${START}" \
    --data-urlencode "end=${END}" \
    --data-urlencode "step=${STEP}") || { echo "  ✗ $NAME (request failed)"; EMPTY=$((EMPTY+1)); continue; }

  POINTS=$(jq '[.data.result[].values | length] | add // 0' <<<"$RESP")
  if [[ "$POINTS" -eq 0 ]]; then
    echo "  ✗ $NAME — NO DATA"; EMPTY=$((EMPTY+1))
  else
    echo "  ✓ $NAME (${POINTS} points)"
  fi

  [[ $DRY -eq 1 ]] && continue
  jq -c --arg run "$RUN" --arg metric "$NAME" --arg query "$QUERY" \
        --arg start "$START" --arg end "$END" --arg step "$STEP" \
     '{run:$run, metric:$metric, query:$query, start:$start, end:$end, step:$step, result:.data.result}' \
     <<<"$RESP" >> "$OUT"
done < "$QUERY_FILE"

echo "→ $((TOTAL-EMPTY))/$TOTAL queries returned data"
[[ $EMPTY -gt 0 ]] && echo "⚠  empty results are instrumentation gaps, not zeros — fix before the real run"
[[ $DRY -eq 1 ]] && echo "→ dry run, nothing written"
exit 0
