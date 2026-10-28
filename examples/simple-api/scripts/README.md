# simple-api/scripts — the machinery behind `../execution.md`

A local cluster with a workload that costs CPU to serve, an HPA that scales it,
Prometheus scraping it per pod, and the runner `report-kit new-point --profile
api` copied here. Running the grid below is what produced every number in
`../execution.md` and `../report.md`.

```bash
./up.sh                                          # kind cluster + workload (~2 min)
./api_point.py --set-freeze                      # once, at the start of the sweep
./api_point.py --run rate-04 --rate 4
./api_point.py --run rate-24 --rate 24           # ends and middle first,
./api_point.py --run rate-12 --rate 12           #   methodology.md §6
./api_point.py --run rate-40 --rate 40           # the range was too small
kubectl -n report-kit-example patch hpa mock-api --type=merge -p '{"spec":{"maxReplicas":1}}'
./api_point.py --run rate-32 --rate 32           # #05, invalid on purpose: one replica
kubectl -n report-kit-example patch hpa mock-api --type=merge -p '{"spec":{"maxReplicas":4}}'
./api_point.py --run rate-32b --rate 32          # #06, the re-run
./down.sh                                        # delete the cluster
```

About **two minutes per point**: 45 s of load (`duration` defaults to 45s in
`../execution.yaml`), ~40 s waiting for the autoscaler to come back down,
20 s of hold, then export and guards.

**Leave a gap between points.** A pod that has just scaled in is still a scrape
target for an interval or two and reports `up == 0`, which fails the next
point's preflight. `./api_point.py --run x --rate 1 --preflight-only` says when
it is clear — 0–20 s in practice.

## Files

| | |
| :--- | :--- |
| `api_point.py` | the runner, from `report-kit new-point`: preflight → load → watch, then `report-kit point finish` |
| `load.js` | k6, constant arrival rate; writes its summary next to the point |
| `env.yaml` | addresses, port-forwards, and the generator command |
| `image-freeze.json` | the image the sweep measured, written by `--set-freeze` |
| `../metrics.yaml` | what is read: M4–M6 exported from Prometheus, M1–M3 from k6's summary in the record, D8 and R9 worked out of it |
| `../execution.yaml` | what a point is run with (`point:`), the deployment the window waits for, and what makes a point invalid |
| `manifests/` | the mock API with its HPA, and Prometheus with per-pod scraping |
| `data/` | what the runs wrote — the evidence `../execution.md` cites |

What is left in `api_point.py` beyond the template is what only this system
knows: how k6's summary reads (`client_summary`, kept unrounded under
`observations.client`, where `../metrics.yaml` reads M1–M3) and that k6's
exit 99 — a breached threshold — is the finding rather than a doubt about the
load. Everything after the window closes is the library's, so
`report-kit point finish data/<run>.point.json --force` re-exports a point and
works out every ref again from the record alone.

It imports `report_kit` like any other package — this example is an ordinary
consumer of the installed kit, which is why a green run here also proves the
install is sound.

## What the run shows

Verified output, not an illustration — `rate-24`, with the watch's per-poll
lines left out and paths shortened:

```
-> preflight
[  ok  ] mock-api at idle — 1 replica(s), idle 1
[  ok  ] prometheus targets up
 warn  not pinned by digest: deployment/mock-api — a tag can move under a frozen name
[  ok  ] image freeze matches
-> generator · k6 run --quiet --summary-export data/rate-24.summary.json -e TARGET_RATE=24 -e DURATION=45s ...
[  ok  ] generator exit 0 · 0h00m45s · data/rate-24.generator.log
-> watching the window close — hold 20s, poll 3s, timeout 0h05m00s
 warn  max_replicas reached: mock-api — this point measures that limit, not the system
[  ok  ] window 2026-10-23T15:14:10Z .. 2026-10-23T15:15:39Z (0h01m28s)
[  ok  ] M4 — 1 series, 6 points          … M5, M6
[  ok  ] guard G1 = 4  [min 1]
[  ok  ] guard G2 = 0  [max 0]
[  ok  ] data/rate-24.point.md
```

and the end of `data/rate-24.point.md`, every ref `../metrics.yaml` defines
worked out of the record by `report-kit point finish`:

```
| M1 | requests served per second | 23.9457 |
| M2 | client-observed latency p95 | 386.372 |
| M3 | share of requests not served | 0 |
| D8 | offered load actually served | 0.997738 |
| R9 | offered rate, the swept axis | 24 |
```

Three details there matter more than the rest.

**`guard G1 = 4`.** G1 counts serving instances, read as of the instant the
load stopped (`guards_at: load_end`, from `events.load_finished`). Asked at
"now" — after scale-in — the same query returns 1. Guards run minutes after
the load ends, so checking them at "now" measures the idle system and passes
quietly.

**`max_replicas reached`.** Every valid point of this grid reaches the HPA's
ceiling of 4, and the record says so under `observations.ceilings_reached`:
the curve describes this autoscaler configuration, not the service.

**The offered rate is not the served rate.** At 40 req/s this cluster served
27.3 and never started 315 iterations. That gap is the finding, and it only
appears because the generator offers load on a schedule instead of waiting for
replies.

## What a local cluster can and cannot test

| Part | In kind | Why |
| :--- | :--- | :--- |
| The whole sync-profile lifecycle | **yes** | this example, end to end |
| `shell`, `proc`, `poll`, `window`, `preflight`, `refs`, `text`, `clock`, `jsonl` | **yes** | no cloud in them at all |
| `prometheus` — query, range, export, guards | **yes** | a real Prometheus, real scrape intervals |
| `portforward` | **yes** | real `kubectl port-forward`, including its habit of dying |
| `cluster.deployment_replicas`, `pods_by_node` | **yes** | plain kubectl reads |
| `reporting.frozen_images` / `check_freeze` | **yes** | kind images are tag-pinned, so it exercises the "not pinned by digest" warning |
| Pod scale-to-zero (the jobs close condition) | **yes, with KEDA** | KEDA runs in kind |
| Queue depth (`cloud.aws.sqs_depth`) | **probably**, untested | the `aws` CLI honours `AWS_ENDPOINT_URL`, so LocalStack should need no code change — nobody has checked |
| `cloud.aws_s3.upload_dir` | **yes, with LocalStack** | it takes the boto3 client as an argument |
| **Node autoscaling** — `nodes_by_selector` reaching zero | **no** | kind nodes are fixed containers; nothing creates or removes them |
| **Interruptions** — `interrupt_events`, `FORCED_REASONS` | **no** | needs Karpenter and real EC2 reclaiming instances |
| **Cost** — `ondemand_hourly`, `spot_hourly` | **no** | real AWS Pricing and spot-history APIs |
| Real capacity values | **no** | one laptop, one node, throttled CPU |

A green run here means the measurement loop is correct. It never means the cost
or validity logic is — those are the parts of the jobs profile that decide
whether a point counts, and they stay untested until they run on a cluster with
a node autoscaler.

## Notes

- `up.sh` installs metrics-server with `--kubelet-insecure-tls`; kind's kubelet
  serving certificates are self-signed and the HPA needs metrics.
- The HPA's `scaleDown.stabilizationWindowSeconds` is cut to 15 s so a demo
  finishes. Kubernetes defaults to 300 s; in a real sweep leave the default and
  set the hold above it, or the window closes during a lull.
- The cluster keeps running after a point. `./down.sh` removes it entirely.
