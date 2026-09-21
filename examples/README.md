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

## Numbers in the examples

Both examples carry a `figures.yaml`, and their documents mark every figure
with a ref. `formats.md` ships into every scaffolded project and tells authors
to do this, so an example that did not would teach the opposite of what the
kit says.

`simple-api/` is the smaller registry: six points, their served rates,
latencies and error shares, plus the served-share column as a formula. It shows
the two cases prose gets wrong on its own — the offered rate is a *setting*
rather than a reading and is registered anyway, because `D8` divides by it, and
the excluded run #05 is registered too, since the document prints its numbers
to explain the exclusion. It also shows one figure rendering two ways: `29.46`
in the matrix and `29.5` in the BLUF are the same ref, because a check compares
the number on the page against what the figure rounds to at the precision that
page chose.

`async-jobs/` is the richer one, and it carries the three things the api
example has no occasion to show:

- **Most of its matrix is derived.** Speed-up is a rate over the baseline rate,
  per-worker efficiency is that speed-up over the pool ceiling. Editing a drain
  cannot leave the efficiency column quietly disagreeing with it.
- **It has an `E` class.** The Expected line is a registered estimate that the
  run then falsified, so the document can print the prediction and the
  measurement side by side and both are checked.
- **One figure is deliberately *not* derived.** `D9` looks like units ÷ drain,
  and is not: the drain is published rounded to a tenth of a second, so
  `1200 / 50.3` gives `23.86` where the record says `23.85`. Precision a
  document threw away cannot be recovered by re-deriving from it, and
  `meta.rounding` says so.

Its §5 guardrail comparing a window rate against a drain rate is left
**uncovered** on purpose — the third state in `formats.md`. The window figure
has no basis in the registry, and inventing one to make the row look verified
is the failure the whole contract exists to prevent.

Both are checkable, and checking them is the point — an example whose numbers
drift teaches the drift:

```bash
report-kit figures --path examples/simple-api/figures.yaml check
report-kit figures --path examples/async-jobs/figures.yaml check
```

## Running one

```bash
pip install -e .                                    # from the repo root

cd examples/simple-api/scripts
./up.sh                                             # kind cluster + workload, ~2 min
./point.py --run demo --rate 8 --duration 45s
./down.sh                                           # delete the cluster

cd examples/async-jobs/scripts
./up.sh                                             # kind + KEDA + workload, ~3 min
./point.py --run demo --n 2 --count 400
./down.sh
```

The two clusters use different names and different port-forwards, so both can
be up at once.

Each example's own `scripts/README.md` carries its grid, its timings and the
traps its runs turned up.
