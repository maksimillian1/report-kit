from __future__ import annotations

import json
from pathlib import Path

from typing import TYPE_CHECKING

from . import shell
from .constants import BAD, EXIT_CLEAN, EXIT_SUSPECT, OK, WARN, die

if TYPE_CHECKING:                    # env.py is the one module needing PyYAML;
    from .env import Env             # a type hint shouldn't drag it in

CONTAINER_PATHS = {
    "scaledjob": ("spec", "jobTargetRef", "template", "spec", "containers"),
    "deployment": ("spec", "template", "spec", "containers"),
    "statefulset": ("spec", "template", "spec", "containers"),
    "daemonset": ("spec", "template", "spec", "containers"),
}


def _dig(node: dict, path) -> list:
    for key in path:
        node = node.get(key, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, list) else []


def frozen_images(env: "Env", refs: list[str]) -> dict[str, list[str]]:
    """refs are 'kind/name'. A sweep claims to compare one artifact across the
    grid; this is what proves it did, by recording the image digests actually
    running. The namespace is resolved per name via env.namespace_for(), since
    the frozen workloads need not all live in one namespace."""
    out: dict[str, list[str]] = {}
    for ref in refs:
        if "/" not in ref:
            die(f"freeze entry must be kind/name, got {ref!r}")
        kind, name = ref.split("/", 1)
        path = CONTAINER_PATHS.get(kind.lower())
        if path is None:
            die(f"cannot read containers from kind {kind!r} — a ScaledObject "
                f"scales an existing workload, so freeze that workload instead")
        namespace = env.namespace_for(name)
        try:
            data = shell.sh_json(["kubectl", "-n", namespace, "get", kind, name,
                                  "-o", "json"])
        except RuntimeError as e:
            raise RuntimeError(f"{ref}: {e}") from None
        out[ref] = sorted(c.get("image", "?") for c in _dig(data, path))
    return out


def check_freeze(freeze_file: Path, current: dict) -> list[str]:
    if not freeze_file.is_file():
        print(f"{WARN} no freeze at {freeze_file} — run --set-freeze first")
        return ["image freeze not recorded"]
    recorded = json.loads(freeze_file.read_text())
    if recorded != current:
        print(f"[{BAD}] image freeze mismatch")
        print(f"         frozen : {json.dumps(recorded, sort_keys=True)}")
        print(f"         current: {json.dumps(current, sort_keys=True)}")
        return ["images differ from the recorded freeze — re-run --set-freeze only "
                "when starting a new sweep"]
    loose = [k for k, v in current.items()
             if any("@sha256:" not in image for image in v)]
    if loose:
        print(f"{WARN} not pinned by digest: {', '.join(loose)} — a tag can move "
              f"under a frozen name")
    print(f"[{OK}] image freeze matches")
    return []


def git_facts() -> dict:
    """The commit under test, and the version of the kit that measured it.

    The two together are a point's provenance. The commit alone used to be
    enough, back when this library sat inside the report's own repository and
    shared its history; as a dependency it has a version of its own, and after
    the fact nothing else in the record says which code produced the numbers.
    """
    from . import version as kit_version

    facts = {"kit_version": kit_version()}
    try:
        facts["commit"] = shell.sh(["git", "rev-parse", "HEAD"]).strip()
        facts["dirty"] = bool(shell.sh(["git", "status", "--porcelain"]).strip())
        print(f"[{OK}] commit = {facts['commit'][:12]}"
              f"{'  (WORKING TREE DIRTY)' if facts['dirty'] else ''}")
    except RuntimeError:
        facts["commit"], facts["dirty"] = "unknown", False
        print(f"{WARN} not a git checkout — the commit goes unrecorded")
    if facts["kit_version"] is None:
        print(f"{WARN} report-kit is not installed — the point record cannot "
              f"say which version of the tooling measured this")
    return facts


def md_table(rows: list[tuple[str, str]]) -> list[str]:
    return ["| | |", "| :--- | :--- |"] + [f"| {a} | {b} |" for a, b in rows]


def write_point(out_dir: Path, run_id: str, markdown: str, record: dict) -> Path:
    """Two artifacts per point. The markdown is pasted into the Journal; the JSON
    is what the cost pass reads its windows from, days later."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{run_id}.point.md"
    md_path.write_text(markdown if markdown.endswith("\n") else markdown + "\n")
    (out_dir / f"{run_id}.point.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n")
    return md_path


def report_validity(doubts: list[str], guard_failures: list[str]) -> int:
    """Prints why a point is in doubt and returns the exit code that says so.

    `doubts` are reasons the run itself is questionable — a node lost while it
    held work, a generator that did not offer the load claimed. They are passed
    in rather than inferred, and printed rather than summarised, because what
    they mean differs: a load generator exiting non-zero can be a malfunction or
    can be the finding (k6 returns 99 when a threshold is breached, which is the
    system failing, not the generator). The caller knows which; this does not."""
    if doubts:
        print()
        print(f"{WARN} {len(doubts)} reason(s) to doubt this point:")
        for doubt in doubts:
            print(f"         · {doubt}")
        print(f"         Re-run it, or mark it \u1d31 and keep it out of the curve "
              f"fit. Do not average it in silently.")
    if guard_failures:
        print()
        print(f"{WARN} guards breached: {', '.join(guard_failures)}")
        print(f"         Apply the matching row of the execution's Validity table "
              f"before the point enters the matrix.")
    return EXIT_SUSPECT if (doubts or guard_failures) else EXIT_CLEAN
