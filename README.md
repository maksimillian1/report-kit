# report-kit

An engineering report framework for decisions ranging from a single-function app to
multi-execution architecture trade-offs. The reasoning behind it is in
[methodology.md](src/report_kit/templates/methodology.md), which `report-kit init`
copies to your report's root.

---

## Installation

```bash
pip install "report-kit @ git+https://github.com/maksimillian1/report-kit@v0.2"

report-kit init docs/report            # 2+ executions
report-kit init docs/report --minimal  # a single execution
```

Nothing is published to a registry: pip clones the tag and builds it. A
private checkout works the same way over `git+ssh://`.

`init` **copies named files out of the package** — the templates, the
methodology, and the two reference documents. Nothing else arrives, and the
library is not copied: it stays a dependency, and each point record carries the
`kit_version` that produced it.

## Profiles

What `report-kit init` writes. `report.md`, `figures.yaml`, `methodology.md`,
`formats.md`, `API.md` and `runners.md` land in both; only the execution layout
differs.

### A · Minimal — one execution

```text
report/
├── report.md
├── figures.yaml                # every number the documents print, resolved in one place
├── methodology.md              # the rules · formats.md · API.md · runners.md — reference, not edited
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
├── figures.yaml                # every number the documents print, resolved in one place
├── methodology.md              # + formats.md · API.md · runners.md
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
| `report-kit figures` | resolve `figures.yaml`, and fail when a number drifts |
| `report-kit export-metrics` | re-export a window whose metrics are aging out |
| `report-kit inspect-metrics` | read back what an export actually captured |
| `report-kit node-cost` | what the nodes cost during a window, the same day |
| `report-kit selftest` | drive both runner templates against a faked cluster |

What the repository holds:

| | |
| :--- | :--- |
| [src/report_kit/](src/report_kit/) | the **library you import** — windows, polling, Prometheus export, guard evaluation, the point record |
| [src/report_kit/templates/](src/report_kit/templates/) | what `init` and `new-point` **copy into a project**: the report and execution documents, the number registry, and the two runners |
| [src/report_kit/tools/](src/report_kit/tools/) | **run as-is**, as the subcommands above |
| [examples/](examples/) | *(repo only)* worked executions, one directory each — [simple-api/](examples/simple-api/) for the api profile and [async-jobs/](examples/async-jobs/) for the jobs one. Each is a local cluster, the runs, and the `execution.md` / `report.md` they produced |

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
| [formats.md](src/report_kit/templates/formats.md) | how a number is written so a script can verify it: how a ref attaches to the digits, which shapes a scan ignores on purpose, and the three states a number can be in |
| [runners.md](src/report_kit/templates/runners.md) | which profile fits your workload, **exactly what inputs to provide** (`env.yaml`, `series.txt`, `guards.txt`, the freeze), the exit-code contract |
| [API.md](src/report_kit/API.md) | the library module by module: what is pure, what talks to a cluster, the one seam to patch when testing |
| [examples/simple-api/scripts/README.md](examples/simple-api/scripts/README.md) | *(repo only)* how to run the api example, and an honest table of what a local cluster can and cannot exercise |
| [examples/async-jobs/scripts/README.md](examples/async-jobs/scripts/README.md) | *(repo only)* the same for the jobs example, plus the three things that make an async point its own profile |

All but the two example READMEs are copied to your report's root by `init`, so
in a project they sit beside `report.md`; the paths above are where they live
in this repository.

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

`examples/async-jobs/` is the same loop for the other profile — a queue, a
worker pool that scales to zero, and a producer running *while* the watch loop
watches. Its ledger carries a whole pass that measured the autoscaler's ramp
rather than the system, and says how that was caught.

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
   `M` measured · `D` derived · `R` recorded · `E` estimated. Definitions neither inherit
   nor get copied; a ref is cited from anywhere by path — `00-baseline/M2`. The *values*
   those refs produce are a separate concern and live in one registry per report,
   `figures.yaml`, written the way
   [formats.md](src/report_kit/templates/formats.md) defines. → §2
3. **Why a metric behaves as it does** is not register material — `concepts.md` as `K⟨n⟩`,
   cited from the register's Notes. → §2
4. **Who is the sentence addressed to?** The report's reader → `report.md`. The author filling
   a template → `methodology.md`. An engineer new to the system → `concepts.md`. Templates
   themselves carry placeholders and nothing else. → §13
5. **Executions are units of work; the report is the unit of decision.** Insignificant results
   are carried into Coverage, not deleted. → §3, §11

---

## Make the check run without being remembered

`figures.yaml` is only worth having if something verifies it. A stale figure is
invisible in a correct-looking table — no reader catches it and no reviewer
questions it — so this is the one failure that survives everything else you do.

Two layers, doing different jobs.

**An editor or agent hook — fast, and not a guarantee.** It puts the contract in
front of whoever is about to edit the report, and runs the check right after. For
Claude Code that is `.claude/settings.json` in the report's repository:

```json
{
  "hooks": {
    "PreToolUse":  [{ "matcher": "Edit|Write", "hooks": [{ "type": "command",
        "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/report-guard.py\"" }] }],
    "PostToolUse": [{ "matcher": "Edit|Write", "hooks": [{ "type": "command",
        "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/report-guard.py\"" }] }]
  }
}
```

Four things that script has to get right, each of which is a way to build one
that looks wired up and does nothing:

- **Filter on `tool_input.file_path`** from the hook's stdin JSON, so it speaks
  up only for files under the report.
- **Never block.** Registering a figure and marking it are two edits, and the
  state between them does not resolve. A hook that refuses an edit refuses every
  intermediate one. Exit 0 on every path, its own failures included.
- **Reach the model through `hookSpecificOutput.additionalContext`.** Plain
  stdout from a `PreToolUse` hook is not added to the context, so printing the
  rules accomplishes nothing.
- **State the contract before, run the checker after.** Checking in `PreToolUse`
  validates the state you are about to replace.

Commit `.claude/settings.json` so the hook travels with the repository; leave
`.claude/settings.local.json` to `.gitignore`, since personal permission
approvals land there.

**CI — slower, and the actual guarantee.** A hook is per-tool and per-machine,
and a pre-commit hook is one `--no-verify` from gone. A job that resolves the
registry and fails the build is what makes the contract hold for a reader nobody
briefed.

What the hook should restate before an edit is the short version of
[formats.md](src/report_kit/templates/formats.md): numbers resolve from the
registry and are never computed in prose; a mark is the ref glued to the digits,
before any closing markup; figures are appended rather than inserted, because
deleting one renumbers every later ref of its class.

The checker is `report-kit figures`. It finds the registry by walking up from the
working directory, so it runs from anywhere inside a report, and `--path` names
one explicitly:

```bash
report-kit figures check              # retired values, ref identity, coverage
report-kit figures validate           # the registry's own rules
report-kit figures block_b_total      # one figure, bare value — by name or by ref
report-kit figures orphans report.md  # currency tokens matching no figure
report-kit figures retype d23_n25 E   # change a kind, renumber every ref
```

Its exit codes are what a CI job needs: **0** clean, **1** something drifted,
**2** the registry is missing or unreadable. `check --strict` promotes a missing
`appears_in` target from a report line to a failure.

Fenced code blocks and inline code spans are skipped whole, so a price quoted
inside an example command is not a claim the checker has to be told to ignore.
A marked number still counts inside backticks: `553.83`(FD7) is an anchor, and
a table cell often wraps the digits that way.

---

## Working on the kit

Four gates. Each has failed before, which is why they are run and not assumed:

```bash
pip install -e ".[dev]"
report-kit selftest                  # both runner templates + node-cost, faked cluster
pytest                               # scaffolding, and the registry's arithmetic and marks
report-kit figures --path examples/simple-api/figures.yaml check
report-kit figures --path examples/async-jobs/figures.yaml check
cd examples/simple-api/scripts  && ./up.sh && ./point.py --run demo --rate 8 --duration 45s
cd examples/async-jobs/scripts  && ./up.sh && ./point.py --run demo --n 2 --count 400
```

The last two are the only checks that the kit still *measures* anything; the
others prove it is wired correctly. The two `figures check` runs are the
examples checking themselves: every marked number in both reports still equals
what the registry resolves to, which is the guarantee the marks exist to give.
`tests/test_figures.py` is one level under that — it checks the checker, because a
mark that silently stops being parsed takes the whole contract with it and the
only symptom is a count going down.

An example runs against the installed package like any other project, so a
green run there is also proof the install works. Run both: they exercise different halves — the api example
never closes a window on a composite condition, and the jobs example never
reads a client-side summary.

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
