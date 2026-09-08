# simple-api/scripts — the machinery behind `../execution.md`

A local cluster with a workload that costs CPU to serve, an HPA that scales it,
Prometheus scraping it per pod, and a ~70-line runner that measures one point.
Running the grid below is what produced every number in `../execution.md` and
`../report.md`.

```bash
./up.sh                                          # kind cluster + workload (~2 min)
./point.py --run rate-04 --rate 4  --duration 45s
./point.py --run rate-24 --rate 24 --duration 45s   # ends and middle first,
./point.py --run rate-12 --rate 12 --duration 45s   #   methodology.md §7
./point.py --run rate-40 --rate 40 --duration 45s   # the range was too small
./point.py --run rate-32 --rate 32 --duration 45s
./down.sh                                        # delete the cluster
```

About **two minutes per point**: 45 s of load, ~40 s waiting for the autoscaler
to come back down, 20 s of hold, then export and guards.

**Leave a gap between points.** A pod that has just scaled in is still a scrape
target for an interval or two and reports `up == 0`, which fails the next
point's preflight. Wait until `up == 0` returns nothing — 0–20 s in practice.

## Files

| | |
| :--- | :--- |
| `point.py` | the runner: preflight → load → hold → export → guards → record |
| `load.js` | k6, constant arrival rate; writes its summary next to the point |
| `env.yaml` | addresses, port-forwards, and the generator command |
| `series.txt` | the Prometheus refs (M4–M6); M1–M3 are client-side, from k6 |
| `guards.txt` | what makes a point invalid — not what makes it interesting |
| `manifests/` | the mock API with its HPA, and Prometheus with per-pod scraping |
| `data/` | what the runs wrote — the evidence `../execution.md` cites |

`point.py` is deliberately smaller than the `api_point.py` template: no image
freeze, git facts, ceiling tracking or exit-code contract. Read this one to
see the shape; run `report-kit new-point` to get the real one.

It imports `report_kit` like any other package — this example is an ordinary
consumer of the installed kit, which is why a green run here also proves the
install is sound.

## What the run shows

Verified output, not an illustration:

```
[  ok  ] mock-api at floor — 1 replica(s)
[  ok  ] prometheus targets up
-> generator · k6 run --quiet --summary-export .../rate-24.summary.json ...
[  ok  ] generator exit 0 · 0h00m45s
-> waiting for scale-in (hold 20s)
    replicas=4                          ← the HPA scaled out under load
    replicas=1 · held 21s               ← held, so the window may close
[  ok  ] window 2026-09-05T19:06:32Z .. 2026-09-05T19:07:55Z (0h01m22s)
[  ok  ] M4 — 1 series, 7 points          … M5, M6
[  ok  ] guard G1 = 4  [min 1]
[  ok  ] guard G2 = 0  [max 0]
```

Two details there matter more than the rest.

**`guard G1 = 4`.** G1 counts serving instances, evaluated at the instant the
load stopped. Asked at "now" — after scale-in — the same query returns 1.
Guards run minutes after the load ends, so checking them at "now" measures the
idle system and passes quietly. That is what `at=` is for.

**The offered rate is not the served rate.** At 40 req/s this cluster served
19.7 and never started 806 iterations. That gap is the finding, and it only
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
| Real capacity figures | **no** | one laptop, one node, throttled CPU |

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
