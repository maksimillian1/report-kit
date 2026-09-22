# report_kit — what's in here and where its edges are

Read this before writing a new run/measurement script. The point of this
package is that a new script should be mostly *your* logic plus calls into
these functions — not a re-derivation of subprocess handling, ref-file
parsing, polling, or guard evaluation that has already been debugged once.

Everything documented here exists in this package. Nothing here depends on
files outside it except where a path is passed in as an argument — that rule
is what lets the same library serve projects with different directory
layouts, and the section below on what it deliberately does not know explains
how far it goes.

## Requirements

Standard library only, except:

| Needed by | Requirement |
|---|---|
| `env.py` | `PyYAML` (import fails loudly with an install hint) |
| `cloud/aws_s3.py` | `boto3` / `botocore` |
| `cloud/aws.py` | the `aws` CLI on PATH (no SDK) |
| `cluster.py`, `portforward.py`, `reporting.frozen_images` | `kubectl` on PATH, working kubecontext |
| `reporting.git_facts` | `git` on PATH |

Import cost is per-module, and deliberately so: **`env.py` is the only
module in the package that needs a third-party package at all.** The time
helpers live in `clock.py` rather than next to `Env` precisely so that
importing a timestamp doesn't drag PyYAML in behind it — otherwise most of
the package would transitively require it, and `report-kit export-metrics`
would stop being a rescue path for a window whose metrics are aging out.
Verified: with `yaml` unimportable, 22 of the 24 modules here still load.
The two that do not are `env.py` itself, by design, and `cloud/aws_s3.py`,
which wants boto3 — and `report-kit export-metrics` still runs.

## Module map

| Module | What it's for | Pure / integration | Public names |
|---|---|---|---|
| `constants.py` | shared status markers + exit codes, `die()` | pure | `OK` `BAD` `WARN` `ARROW`, `EXIT_CLEAN` `EXIT_PREFLIGHT` `EXIT_EXPORT_GAP` `EXIT_SUSPECT` `EXIT_TIMEOUT`, `die` |
| `env.py` | YAML config access | `Env` reads a file | `Env`, `execution_dir` |
| `clock.py` | UTC now, RFC3339, duration formatting | pure | `utcnow`, `rfc3339`, `parse_instant`, `hms` |
| `shell.py` | subprocess and HTTP, JSON-decoded | integration — **the seam** | `sh`, `sh_json`, `http_json` |
| `refs.py` | `ref\|…` pipe-file parsing, guard bounds with `{sub}` placeholders | pure | `read_ref_file`, `load_guards` |
| `prometheus.py` | queries, target health, guard evaluation, exporting a window | integration | `prom_query`, `prom_query_range`, `prom_scalar`, `prom_targets_down`, `check_guards`, `export_range`, `Export` |
| `cluster.py` | kubectl introspection (nodes, pods-per-node, replicas, interrupt events) | integration | `nodes_by_selector`, `pods_by_node`, `deployment_replicas`, `interrupt_events`, `FORCED_REASONS`, `INTERRUPT_REASONS` |
| `portforward.py` | `kubectl port-forward` lifecycle incl. relaunch-on-death | integration, background procs | `PortForwards`, `forward_spec` |
| `reporting.py` | image freeze, git facts, result block writing | mixed | `frozen_images`, `check_freeze`, `git_facts`, `md_table`, `write_point`, `report_validity`, `CONTAINER_PATHS` |
| `jsonl.py` | reading the exported metrics `.jsonl`, and splitting a series at the instant it settled | pure | `load_lines`, `parse_values`, `label_summary`, `changes`, `split`, `NOISY_LABELS` |
| `poll.py` | "retry until condition" and "until it has *held*" | pure (does no I/O itself) | `poll_until`, `wait_until_stable` |
| `text.py` | filename sanitising, `{token}` substitution | pure | `safe_filename`, `fill` |
| `window.py` | the measured interval as one object | pure | `Window` |
| `proc.py` | running load: blocking, or in the background | integration (subprocess) | `run_logged`, `Completed`, `Background` |
| `preflight.py` | a checklist that collects every failure before stopping | prints; no I/O of its own | `Preflight` |
| `dbs/qdrant.py` | Qdrant point counts / collection reset | integration | `points_count`, `delete_collection_if_nonempty` |
| `cloud/aws.py` | SQS depth/purge, S3 prefix wipe, EC2 lookup and on-demand / spot pricing | integration (via `aws` CLI) | `sqs_depth`, `sqs_purge`, `s3_rm_recursive`, `describe_instances`, `ondemand_hourly`, `spot_hourly`, `LOCATION_BY_REGION` |
| `cloud/aws_s3.py` | concurrent directory upload with skip-existing | integration (boto3) | `upload_dir`, `object_exists` |

A new data store goes in `dbs/<store>.py`; a new provider in
`cloud/<provider>.py`. Those files don't exist until something needs them —
there are no stubs to fill in.

## Two things this package deliberately does not know

**Where your project's directories are.** There is no `SCRIPTS_DIR` or
`REPORT_ROOT` derived from `__file__`. A package that gets copied between
repos cannot guess its own depth inside them, and guessing wrong resolves
silently to the wrong place. So `execution_dir(report_root, execution)`
takes the root, `Env(path)` takes the config path, and `write_point(out_dir, …)`
takes the output directory. Your script decides; it's the thing that knows.

**What your metrics backend is** — with one exception. Prometheus is
assumed: `prometheus.py` speaks its query API directly rather than hiding it
behind an interface that would have exactly one implementation. Exporting a
window is `prometheus.export_range()`, in the library; there is no external
exporter script to point at. (`report-kit export-metrics` is a thin CLI over
the same function, for re-exporting a window by hand — it imports only
prometheus/refs/shell/constants/window, all standard-library-only, so it
still works if the parts of this package that need PyYAML or boto3 are
broken. Retention makes that worth keeping: a window can be re-exported but
never re-measured.)

## Testing seams

Almost everything integration-shaped bottoms out in three functions —
`shell.sh`, `shell.sh_json`, `shell.http_json`. `cluster.py`,
`prometheus.py`, `portforward.py`, `dbs/qdrant.py`, `cloud/aws.py` and
`reporting.frozen_images`/`git_facts` never shell out or open a socket
themselves. So:

```python
with patch("report_kit.shell.sh_json", return_value={"items": [...]}):
    assert cluster.deployment_replicas("ns", "api") == 3
```

That's the whole testing story — stdlib `unittest.mock`, no fixture DSL, no
fake Kubernetes, no request matchers. `report-kit selftest` drives both
runner templates and `node-cost` end to end on exactly those three patches,
so the claim is checked rather than asserted.

**This only holds because callers say `shell.sh_json(...)`, not
`sh_json(...)`.** A module doing `from .shell import sh_json` binds the
function into its own namespace at import time, and patching
`report_kit.shell.sh_json` afterwards would not affect it — the test would
silently run against the real cluster or fail confusingly. Every module here
imports `from . import shell` and calls through the module object. Keep doing
that in anything you add.

Two exceptions, both easier:

- `cloud/aws_s3.py` takes the boto3 client as an argument (`s3=`), so pass a
  `Mock()` instead of patching anything.
- `poll.poll_until` takes the callable it polls, so hand it a fake `check`.

Pure modules (`refs`, `jsonl`, `text`, `env`'s time helpers, `reporting`'s
`md_table`/`report_validity`) need no seam at all.

## Sync and concurrency: four shapes, no fifth

There is no `asyncio` in this package and adding it would buy nothing —
every wait here is either a subprocess or an HTTP call, and the four shapes
below already cover them. Pick the one matching the work.

**1 — Blocking subprocess.** You need the result and have nothing else to do.

```python
out = shell.sh(["kubectl", "get", "ns"])            # raises RuntimeError on failure
```

**2 — Background process + poll.** Something must run while you watch
something else. `proc.Background` is this shape, written once:

```python
with Background(cmd, log_path) as producer:      # starts immediately
    window = watch(...)                          # runs while it works
    if producer.poll() is None:
        print("the system finished before the producer did")
```
It kills the child by process group on exit, so a failure in the watch loop
can't leave a producer writing into the next run's window.
`portforward.PortForwards` is the long-lived variant, with `ensure_alive()`
to relaunch a tunnel that dropped mid-run.

**3 — Thread pool, I/O-bound fan-out.** N independent network calls.

```python
with ThreadPoolExecutor(max_workers=16) as pool:
    futures = {pool.submit(fn, item): item for item in items}
    for f in as_completed(futures):
        f.result()                                   # re-raises the first failure
```
`cloud/aws_s3.upload_dir` is this shape, already written — use it rather
than rebuilding an upload loop. `proc.run_logged` covers the blocking case
with the timing captured (shape 1 plus a `Window`).

**4 — Process pool, CPU-bound fan-out.** N independent heavy transforms
(parsing, decompression). Same code as 3 with `ProcessPoolExecutor`, and
the work function must be importable and its arguments picklable. Don't mix
these up: threads for waiting, processes for computing.

**Waiting for a condition** is not a fifth shape — it's `poll.py`, and which
of its two functions you want is a real decision:

```python
poll.poll_until(check, poll_seconds=…, max_wait_seconds=…)          # true once
poll.wait_until_stable(check, hold_seconds=…, poll_seconds=…,       # true, and stayed
                       max_wait_seconds=…)
```
Use `wait_until_stable` for anything that closes a measurement window.
"The queue is empty" is not the same claim as "the queue has been empty for
a minute": a queue reads zero while messages are still in flight, a
deployment touches its floor between two scaling decisions, and closing on
the instantaneous reading records a point that measured half a run. It
returns the instant the condition *first* held, so the caller decides
whether the confirmation buffer counts as part of the window.

Both own only the timeout arithmetic and tolerating one failed poll.
Anything richer — tracking a peak, keeping a port-forward alive inside the
same loop, closing on several conditions at different times — goes in your
`check` closure. Don't grow either into a scheduler.

## Conventions when adding to this package

- Decide pure vs. integration first. Pure logic goes in a plain module and
  gets a test; anything touching the outside world goes through `shell.py`,
  or into `dbs/<store>.py` / `cloud/<provider>.py`.
- No shared base classes across stores or providers. Qdrant's
  404-means-empty quirk and Postgres' transaction handling have nothing in
  common; a common interface would only hide that. Duplication between two
  store files is fine.
- Functions return values and raise; they don't print status and exit. The
  exceptions are `die()` (explicitly fatal), `check_guards`/`check_freeze`
  and `report_validity`, which exist to print a verdict. New utilities
  should follow the first rule, so a caller can decide what to say.
- Take paths, clients, and callables as arguments instead of constructing
  them from assumptions. That's what makes these testable and portable.
- Reach the outside world as `shell.sh_json(...)`, never `from .shell import
  sh_json` — see the seam note above. `report-kit selftest` fails loudly
  if something breaks this.
- Don't add a matcher library, a plugin registry, or a config DSL. The
  specific detail of one run — this query, this threshold, this glue — is
  cheap to write fresh in the calling script. What belongs here is the
  narrow stuff that is easy to get subtly wrong twice: timeout arithmetic,
  ref-file parsing, 404-vs-empty distinctions, skip-existing upload logic.

## Using it: the runners and the tools

Two things sit beside this library, and the split between them is the point:

- **`templates/runners/`** — exactly two scripts, `api_point.py` (synchronous
  request/response workload) and `jobs_point.py` (asynchronous queue/worker
  one). `report-kit new-point` **copies one into an execution** for you to
  edit: each has a CONSTANTS block naming what must not move during a sweep.
  They are not a framework — nothing subclasses anything, and a run is the
  body of `main()`, readable top to bottom. The copy is deliberate: a runner
  edited in place would change what the earlier points of the same sweep
  measured.
- **`tools/`** — `figures`, `export_metrics`, `inspect_metrics`, `node_cost`,
  `selftest`, reached as `report-kit <name>`. Generic CLIs that **work
  unedited** in any project, and the reason `cli.py` imports a subcommand only
  after the arguments are parsed. A tool's model sits above its `cmd_*`
  functions and prints nothing, so `from report_kit.tools.figures import
  Registry` gets a script a value rather than a page. Generic CLIs that **work unedited** in any
  project, and the reason `cli.py` imports a subcommand only after the
  arguments are parsed.

`runners.md` explains which profile to start from and what to change. If you
are writing a new measurement script, start there, not from a blank file.

---

## Why some of this is opinionated

`refs.py` and `reporting.py` encode one specific measurement methodology — the
one in `methodology.md`, which `report-kit init` puts at your report's
root. A "point" is one measured run; `series.txt` is
`ref|promql` exported per point; `guards.txt` is `ref|bound|promql` checked at
the window's close; a frozen set of image digests proves a whole sweep measured
one artifact. Reuse those two modules if that methodology fits, and ignore them
if it does not — nothing else here depends on them.

`cluster.FORCED_REASONS` is similarly specific: it lists the node-loss reasons
that invalidate a window on EKS with Karpenter, as distinct from ordinary
consolidation. The distinction was established by observation rather than from
documentation. Keep it on Karpenter; replace it elsewhere.

`constants.EXIT_*` is the exit-code contract the runners share — 2 means data
was lost, 3 means the run happened but is suspect, 4 means it never converged.
Worth keeping as a convention; nothing enforces it.
