"""The two ways a chart run stops: one chart, or the whole run."""

from __future__ import annotations


class ChartError(Exception):
    """The environment or the arguments make every chart impossible."""


class Skip(Exception):
    """One chart has no usable rows. Reported on stderr; the rest render."""
