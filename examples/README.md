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
| — | jobs — queue/worker | **none.** The runner template has only ever run against `report-kit selftest`'s fakes |

The missing row is the honest one. A jobs example needs a queue, a worker
pool and a node autoscaler; `simple-api/scripts/README.md` has the table of
what a local cluster can and cannot exercise, and node autoscaling, instance
interruption and real cost are all on the wrong side of it. Those are exactly
what decides whether a jobs point is *valid*, so no local example would
exercise the part that matters.

## Running one

```bash
pip install -e .                                    # from the repo root
cd examples/simple-api/scripts
./up.sh                                             # kind cluster + workload, ~2 min
./point.py --run demo --rate 8 --duration 45s
./down.sh                                           # delete the cluster
```

Each example's own `scripts/README.md` carries its grid, its timings and the
traps its runs turned up.
