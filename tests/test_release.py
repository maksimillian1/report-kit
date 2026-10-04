"""The version a reader installs is the version the package declares.

    pytest tests/test_release.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECLARED = re.compile(r'^version = "([^"]+)"$', re.MULTILINE)
PINNED = re.compile(r"report-kit[^\s\"']*@v([0-9][^\s\"']*)")


def declared() -> str:
    return DECLARED.search((ROOT / "pyproject.toml").read_text(encoding="utf-8")).group(1)


def test_readme_installs_the_current_version():
    pins = PINNED.findall((ROOT / "README.md").read_text(encoding="utf-8"))
    assert pins, "README.md names no tag to install"
    assert set(pins) == {declared()}, (
        f"README.md installs v{', v'.join(sorted(set(pins)))}; "
        f"pyproject.toml declares {declared()}")
