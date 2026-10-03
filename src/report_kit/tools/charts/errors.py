"""The two ways a chart run stops: one chart, or the whole run."""

from __future__ import annotations


class ChartError(Exception):
    """The run stops."""


class Skip(Exception):
    """One chart stops. Reported on stderr; the rest render."""
