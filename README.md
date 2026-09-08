# report-kit

An engineering report framework for decisions ranging from a single-function app to
multi-execution architecture trade-offs. The reasoning behind it is in
[methodology.md](src/report_kit/templates/methodology.md), which `report-kit init`
copies to your report's root.

---

## Installation

```bash
pip install "report-kit @ git+https://github.com/maksimillian1/report-kit@v0.1"

report-kit init docs/report            # 2+ executions
report-kit init docs/report --minimal  # a single execution
```

Nothing is published to a registry: pip clones the tag and builds it. A
private checkout works the same way over `git+ssh://`.

The tag has to exist on the remote — `git tag v0.1 && git push --tags`. Pin to
a tag rather than a branch: a report's numbers were produced by one version of
this code, and `@master` would quietly become a different one.

`init` **copies named files out of the package** — the templates, the
methodology, and the two reference documents. It is not a download that
deletes what does not belong, which is what the old `bootstrap.sh` was; the
difference is that a file added to this repo now reaches a project only if
somebody names it in `scaffold.py`. `tests/test_scaffold.py` asserts both
directions of that.

The library itself is **not** copied into your project. It is a dependency,
and each point record carries the `kit_version` that produced it — which is
better provenance than a pin written once at `init` time, because it records
what actually ran, per point, and cannot drift from it.

## Profiles

What `report-kit init` writes. `report.md`, `methodology.md`, `API.md` and
`runners.md` land in both; only the execution layout differs.

### A · Minimal — one execution

```text
report/
├── report.md
├── methodology.md              # the rules · API.md · runners.md — reference, not edited
├── assets/                     # charts, once something renders one
└── execution/
    ├── index.md                # 1 Givens · 2 Plan · 3 Journal · 4 Results
    ├── concepts.md             # optional — when the block outgrows index.md
    ├── metrics.md              # optional — when the register outgrows index.md
    ├── data/                   # what a run writes, named by its Point
    └── scripts/                # ← report-kit new-point puts the runner here
```

### B · Full — 2+ executions

```text
report/
├── report.md
├── methodology.md              # + API.md · runners.md
├── assets/
└── executions/
    ├── 00-baseline/            # 1 Plan · 2 Results
    │   ├── index.md
    │   ├── concepts.md
    │   ├── metrics.md
    │   ├── data/
    │   └── scripts/            # ← report-kit new-point
    └── 01-⟨name⟩/              # 1 Plan · 2 Journal · 3 Results
        └── …
```

**There is one `scripts/` now, and it belongs to an execution.** The library
is a dependency and the tools are subcommands, so nothing shared sits at the
report root — the only thing on disk is the runner copy that defines this
execution's points.

---

## Two execution templates

The flows diverge, so the templates are separate files. Do not use one for the other.

* **Minimal (`execution/index.md`)** — 1 Givens, 2 Plan, 3 Journal, 4 Results. The metric
  register is a given: instrumentation is never under test. Preflight closes §1, so the
  checklist gates only what stands above it. Routing targets the report directly.
* **Full (`executions/NN-⟨name⟩/index.md`)** — 1 Plan, 2 Journal, 3 Results. Givens are
  inherited from `00-baseline` §2 and cited from there.

**Migration A → B** is the one operation that rewrites existing files: `execution/` becomes
`executions/00-baseline/` plus `01-⟨name⟩/`, and §2 Givens moves into the baseline. Do it
before the second execution runs.

---

## Tooling

One command, installed with the package:

| | |
| :--- | :--- |
| `report-kit init` | write the report skeleton for a layout |
| `report-kit new-point` | copy a runner and its inputs into one execution |
| `report-kit export-metrics` | re-export a window whose metrics are aging out |
| `report-kit inspect-metrics` | read back what an export actually captured |
| `report-kit node-cost` | what the nodes cost during a window, the same day |
| `report-kit selftest` | drive both runner templates against a faked cluster |

Behind them are three kinds of thing, and the distinction is the whole design:

| | |
| :--- | :--- |
| [src/report_kit/](src/report_kit/) | the **library you import** — windows, polling, Prometheus export, guard evaluation, the point record |
| [src/report_kit/templates/](src/report_kit/templates/) | what `init` and `new-point` **copy into a project**: the report and execution documents, and the two runners |
| [src/report_kit/tools/](src/report_kit/tools/) | **run as-is**, as the subcommands above |
| [examples/](examples/) | *(repo only)* worked executions, one directory each. [simple-api/](examples/simple-api/) is a complete one: a local cluster, the runs, and the `execution.md` / `report.md` they produced |

**A runner is copied, not imported.** It lands in the execution's `scripts/`
beside its own `env.yaml`, `series.txt` and `guards.txt`, because the axis is
under test and what defines it belongs to the execution. A runner edited in
place would silently change what earlier points of the same sweep measured.

### Requirements

Standard library only, except: `PyYAML` for `env.py` — the one module in the
package that needs a package at all, and installed for you — `boto3` for
`cloud/aws_s3.py` (`pip install "report-kit[s3]"`), and the `aws` / `kubectl`
/ `git` CLIs for the modules that shell out to them.
Prometheus is assumed as the metrics backend and spoken to directly, rather
than hidden behind an interface with one implementation.

### Where the detail lives

| | |
| :--- | :--- |
| [runners.md](src/report_kit/templates/runners.md) | which profile fits your workload, **exactly what inputs to provide** (`env.yaml`, `series.txt`, `guards.txt`, the freeze), the exit-code contract |
| [API.md](src/report_kit/API.md) | the library module by module: what is pure, what talks to a cluster, the one seam to patch when testing |
| [examples/simple-api/scripts/README.md](examples/simple-api/scripts/README.md) | *(repo only)* how to run the worked example, and an honest table of what a local cluster can and cannot exercise |

Both of the first two are copied to your report's root by `init`, so in a
project they sit beside `report.md`; the paths above are where they live in
this repository.

### Start here

```bash
cd examples/simple-api/scripts && ./up.sh && ./point.py --run demo --rate 8 --duration 45s
```

`examples/simple-api/` is the whole loop end to end: `scripts/up.sh` brings
up a local cluster, six runs of `scripts/point.py` produce the ledger in
`execution.md`, and `report.md` is what those rows support.
One of the six is invalid — it ran against the wrong replica count — and is
carried as a row rather than deleted, which is the part worth reading.
Every number in both documents came out of a run — which is also why their cost
sections are empty rather than plausible.

---

## Order of operations — first revision

Every step below is forward-only: skip it and the figure cannot be reconstructed later
(`methodology.md` §6). Steps 1–6 are preparation, not runs — they produce a freeze commit
and a journal note.

1. **Freeze the system.** Tag the commit under test. Nothing below survives a rebuild.
2. **Confirm metric names against live endpoints.** Date each confirmation in the register.
   An unconfirmed ref cannot appear in a Plan, which makes this the first real gate.
3. **Verify cost attribution tags are active in IaC.** Tagging is forward-only; a tag added
   late yields a partial month and no way to tell which part.
4. **Capture the price basis** → `data/price-⟨date⟩.json`. An undated basis invalidates every
   derived figure downstream.
5. **Freeze the input fixture** → `data/⟨name⟩-profile.txt`. Record the exact count on a
   batch path; on a serving path record the request mix and what counts as a unit.
6. **Write the Expected line**, dated, before the first run — the baseline included.
7. **Capture the floor** over a window with zero execution points. Split A / B / C.
8. **Write the Coverage rows** in `report.md`, statuses left unresolved.
9. **Freeze the first execution's Plan**, then run.

---

## Rules of placement

1. **Is it under test?** No — a given: `00-baseline` §2, or minimal §1. Yes — an axis:
   `NN-⟨name⟩` §1 Plan, or minimal §2 Plan. Changing a given is preparation, not a run. → §2
2. **Every metric is defined once**, in the execution that uses it, and carries a ref.
   `M` measured · `D` derived · `R` recorded · `E` estimated. No global register, no
   inheritance; cite across executions by path — `00-baseline/M2`. → §2
3. **Why a metric behaves as it does** is not register material — `concepts.md` as `K⟨n⟩`,
   cited from the register's Notes. → §2
4. **Who is the sentence addressed to?** The report's reader → `report.md`. The author filling
   a template → `methodology.md`. An engineer new to the system → `concepts.md`. Templates
   themselves carry placeholders and nothing else. → §13
5. **Executions are units of work; the report is the unit of decision.** Insignificant results
   are carried into Coverage, not deleted. → §3, §11

---

## Working on the kit

Three gates. Each has failed before, which is why they are run and not assumed:

```bash
pip install -e .
report-kit selftest                  # both runner templates + node-cost, faked cluster
python3 tests/test_scaffold.py       # every template ships, and nothing else does
cd examples/simple-api/scripts && ./up.sh && ./point.py --run demo --rate 8 --duration 45s
```

The last one is the only check that the kit still *measures* anything; the
first two only prove it is wired correctly. An example runs against the
installed package like any other project, so a green run there is also proof
the install works.

The rules live next to what they constrain —
[src/report_kit/API.md](src/report_kit/API.md) for the library's contract,
[templates/runners.md](src/report_kit/templates/runners.md) for what a point
needs and the traps it encodes, and
[templates/methodology.md](src/report_kit/templates/methodology.md) for what
makes a figure credible. Restating them here would only produce a second copy
to keep in step.

Three rules belong to the repo itself and are enforced nowhere else:

- **Subcommands are imported lazily.** `cli.py` holds module *names* and
  resolves one only after the arguments are parsed. `export-metrics` exists
  for the day a run finished, its export did not, and retention is counting
  down; importing every tool up front would drag `env` and PyYAML into a
  command that needs neither, and the rescue path would break exactly then.
  Check it: `python -c "import sys; sys.modules['yaml']=None;
  from report_kit.cli import main; main(['export-metrics','--help'])"`.
- **`templates/` ships verbatim, so no bytecode may travel with it.** The two
  runners in it are `.py` files, and anything that imports or compiles them —
  `selftest`, a stray `compileall src/`, an editor — leaves a `__pycache__`
  in the source tree, and `package-data` would otherwise sweep it into the
  wheel. What actually protects the wheel is `exclude-package-data`, checked
  by building one with a planted `.pyc` and confirming it is absent;
  `selftest` additionally turns bytecode writing off so a normal run leaves
  nothing behind. Local residue is expected and harmless — `.gitignore`
  covers it. The scaffold test caught this the first time.
- **`templates/runners/` holds exactly two runners.** A third is right when a
  third *profile* appears, not when a helper does. Run-as-is goes in `tools/`
  as a subcommand, importable goes in the library.
