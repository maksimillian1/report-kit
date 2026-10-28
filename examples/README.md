# examples/

Worked executions, one directory each. They are repo-only — `report-kit init`
never copies them into a project — and they exist for two jobs: to show what a
filled-in `execution.md` and `report.md` actually look like, and to be the
gate that proves the kit still measures something.

Each is an ordinary consumer of the installed package. Nothing here imports
the library by path, so a green run in one of these is also proof that
`pip install report-kit` produced a working install.

| | Profile | Status |
| :--- | :--- | :--- |
| [`simple-api/`](simple-api/) | api — request/response | complete: a local cluster, six runs, and the two documents they support |
| [`async-jobs/`](async-jobs/) | jobs — queue/worker | complete for the **measurement loop**: a queue, a pool that scales to zero, ten runs. Node autoscaling, interruption and cost stay untested — see below |
| [`priced-api/`](priced-api/) | api — request/response, priced | complete for the **price wiring**: the same service on k3s beside OpenCost, kube-state-metrics and cAdvisor, three runs, every price line in the register worked into a cost per point — **at invented rates**, so its dollars are arithmetic, not anyone's bill |
| [`tenant-platform/`](tenant-platform/) | none — charts only | **invented numbers**, no cluster and no execution: one CSV per chart shape and flag, for the cost and time-axis charts the two real examples cannot produce |

The jobs row used to read *none*, on the argument that a local cluster cannot
autoscale nodes, cannot have an instance taken away, and cannot price
anything — and that those are what decide whether a jobs point is *valid*.

Half of that argument was wrong. The clause those three feed is "is anything
still allocated to this work?", and KEDA answers it locally one layer down:
the worker pool scales to **zero**, so the composite close condition, the
retry queue that refills after the work queue reads empty, and the counters
that have to outlive a pool that went away are all exercised for real. What
remains out of reach is everything *downstream* of that answer — what the
allocation cost, and whether it was taken away involuntarily.
`async-jobs/scripts/README.md` draws the line explicitly.

The example paid for itself on the way in: `jobs_point.py` could close a
zero-length window over a system that had never done any work, and
`selftest` was asserting `window >= 0`, so its own gate passed on it. Both
are fixed. That is what an example is for.

## The priced example

`priced-api/` answers the question the other two leave open — can a local
run carry what it cost? — for everything up to the rate. OpenCost prices the
cluster with rates its ConfigMap invents, publishes them into the same
Prometheus the runner exports from, and the register works a cost per point
out of them: the pool's nodes, the service's requests, its volume, its load
balancer and the control-plane fee. So the queries `runners.md` recommends
have run against a real OpenCost, and the two traps it lists were found here:
OpenCost's allocation runs a minute behind the pods it allocates, and
OpenCost republishes kube-state-metrics' series, so a request summed without
`job=` counts twice.

What it cannot show is a price anyone charges. Its node is not an EC2
instance, so `prices_match_aws` — which holds every price OpenCost published
against AWS's — stays off in its `execution.yaml`, and is exercised by
`selftest` and `tests/test_price_check.py` against fakes. Until a point runs
with it on a real EKS cluster, treat its first verdict there as unverified.

## Numbers in the examples

Each measured example carries a `report-values.yaml`, and its documents mark every value
with a ref. `formats.md` ships into every scaffolded project and tells authors
to do this, so an example that did not would teach the opposite of what the
kit says.

`simple-api/` is the smaller registry: six points, their served rates,
latencies and error shares, plus the served-share column as a formula. It shows
the two cases prose gets wrong on its own — the offered rate is a *setting*
rather than a reading and is registered anyway, because `D8` divides by it, and
the excluded run #05 is registered too, since the document prints its numbers
to explain the exclusion. It also shows one value rendering two ways: `31.33`
in the matrix and `31.3` in the BLUF are the same ref, because a check compares
the number on the page against what the value rounds to at the precision that
page chose.

`async-jobs/` is the richer one, and it carries the three things the api
example has no occasion to show:

- **Most of its matrix is derived.** Speed-up is a rate over the baseline rate,
  per-worker efficiency is that speed-up over the pool ceiling. Editing a drain
  cannot leave the efficiency column quietly disagreeing with it.
- **It has an `E` class.** The Expected line is a registered estimate that the
  run then falsified, so the document can print the prediction and the
  measurement side by side and both are checked.
- **Its headline is worked out by the kit, not by the runner.** `D8`, the
  drain, is `events.drained - events.load_started` — two instants the runner
  records unrounded — and `D9` is the completed count over it. The runner
  computes no number a document prints; `report-kit point finish` and
  `values pull` both get there from the record, so a drain printed to a tenth
  and a rate printed to a hundredth are one piece of arithmetic, not one
  recomputed from the other's printed form. `meta.rounding` says so.

Its §5 guardrail comparing a window rate against a drain rate is left
**uncovered** on purpose — the third state in `formats.md`. The window value
has no basis in the registry, and inventing one to make the row look verified
is the failure the whole contract exists to prevent.

Every value a run's data holds also names it with `from:` — each measured
value, and each setting a point record carries — so `values pull` is how the
values got into the registry, and `check` re-reads every one of them from
`scripts/data/`. `tier_service_*` is the case that needed it: the registry had
stored them rounded to a tenth, where the export gives them at full precision.
Each registry's `points:` block says once what one run adds, and every value of
a grid point carries the `point:` key that `adopt-point` gave it, so a point can
be renamed or deleted as a set.

Both are checkable, and checking them is the point — an example whose numbers
drift teaches the drift:

```bash
report-kit values --path examples/simple-api/report-values.yaml check
report-kit values --path examples/async-jobs/report-values.yaml check
```

## Running one

```bash
pip install -e .                                    # from the repo root

cd examples/simple-api/scripts
./up.sh                                             # kind cluster + workload, ~2 min
./api_point.py --run demo --rate 8                 # --duration defaults to 45s
./down.sh                                           # delete the cluster

cd examples/async-jobs/scripts
./up.sh                                             # kind + KEDA + workload, ~3 min
./jobs_point.py --run demo --n 2 --count 400
./down.sh

cd examples/priced-api/scripts
./up.sh                                             # onto the current context — a k3s cluster
./api_point.py --run demo --rate 8
./down.sh                                           # what up.sh applied; the cluster stays
```

The two kind clusters use different names and different port-forwards, so
both can be up at once. `priced-api` creates no cluster: its
`scripts/README.md` says which one its runs used and why not kind.

Each example's own `scripts/README.md` carries its grid, its timings and the
traps its runs turned up.
