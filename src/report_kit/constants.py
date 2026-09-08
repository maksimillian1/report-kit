from __future__ import annotations

import sys

OK, BAD, WARN, ARROW = "  ok  ", " FAIL ", " warn ", "->"

# Identical across runners, so the Journal describes one contract.
EXIT_CLEAN = 0
EXIT_PREFLIGHT = 1
EXIT_EXPORT_GAP = 2
EXIT_SUSPECT = 3
EXIT_TIMEOUT = 4

# No SCRIPTS_DIR/REPORT_ROOT here on purpose. Deriving them from __file__
# would bake one repo's directory depth into a package whose whole point is
# being copied into others, where it would resolve to the wrong place
# silently. Functions that need a root take it as an argument instead.


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(EXIT_PREFLIGHT)
