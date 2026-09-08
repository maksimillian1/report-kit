"""report-kit — measurement utilities for engineering reports.

Importing this package pulls in nothing else: the modules underneath are
imported individually, and only `env` needs a third-party package. That is
deliberate — `API.md`, next to this file, explains the seams and why.
"""

from __future__ import annotations

__all__ = ["__version__", "version"]


def version() -> str | None:
    """The installed version, or None when running from a source tree.

    A point record carries this. The library used to live inside the report's
    own repository, so its commit was the provenance; now it is a dependency,
    and nothing else in the record would say which code produced the numbers.
    None is the honest answer for an uninstalled checkout — better than a
    version string invented to fill the field.
    """
    from importlib.metadata import PackageNotFoundError, version as _version
    try:
        return _version("report-kit")
    except PackageNotFoundError:
        return None


__version__ = version() or "0.0.0+unknown"
