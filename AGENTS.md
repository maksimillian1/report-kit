# report-kit — agent instructions

Applies to this repository only. Gates and repo rules: README.md, "Working on the kit".

## Commands

```bash
pip install -e ".[dev]"
git config core.hooksPath .githooks
pytest
report-kit charts --all && report-kit charts --check
```

## Code

- Names carry the meaning. A function says what it returns or does (`read_spec`, `staleness`),
  a constant says its role (`LINEAR_MAX_SPAN`, not `LOG_SPAN  # why`). When a line seems to need
  a comment, rename or extract a function first.
- A comment is kept only for what the code cannot show: a library quirk, an ordering trap, a
  deliberate absence. Expect a handful per package, not one per function. No section banners,
  no docstring that restates the signature; rationale goes in `API.md` or `templates/formats.md`.
- One function, one job, readable without scrolling (about 40 lines). A branch that needs
  explaining becomes a named helper.
- One module, one reason to change: `table.py` the CSV format, `kinds.py` the shapes, `spec.py`
  `charts.yaml`. A new reason is a new module, and a package's `__init__.py` is its command only.
- Functions over classes, frozen dataclasses for data, no interface or base class with one
  implementation.
- No consumer's names or numbers in `src/`, `templates/` or `examples/`. Invent neutral ones that
  agree with each other, and say they are invented.
- Every behaviour change ships with a test in `tests/` that fails without it.
- The chart CSV format is frozen. A new need goes into `charts/charts.yaml` or a flag, not into a
  new rule about columns.

## Releases and method

- The version lives in `pyproject.toml` only. README's install line names the same tag, and
  `tests/test_release.py` fails when it does not.
- Bump the version in the change's own branch. Tag `v<version>` on master after the merge, never
  on the branch: merges are squashed, so a branch commit is not in master's history.
- `templates/` is copied into other repositories, and `formats.md` and `methodology.md` are
  vendored byte for byte. A change there is a release note, and a renumbered section breaks every
  report that cites it.
