"""Report §3: what throughput costs, on either profile.

Each chart passes the label placement that suits its own geometry as `first`:
centred above a mark on a shallow curve, beside one on a steep curve, where
directly above would land on the line.
"""

from __future__ import annotations

from pathlib import Path

from . import canvas
from .canvas import (HAIRLINE, LINE_W, MARKER_SZ, TYPE_LABEL, annotate,
                     axis_label, headroom, hollow, legend, new_figure,
                     panel_label, save, style_axis, thousands)
from .contract import (cell, flag, header_of, num, period_of,
                       replica_series, unit_of)
from .errors import Skip
from .labels import ABOVE, BESIDE, BESIDE_BELOW, LABEL_DY, place_label, renderer_for


# Three is the most a reader separates on one frame; a fourth reuses the first.
SERIES_STYLES = ("-", (0, (6, 4)), (0, (2, 3)))


def jobs_axis(rows) -> tuple[str, str]:
    """`n_reached` where the run measured what it held, `n_set` where it
    recorded only the ceiling it was given."""
    if any(num(r, "n_reached") is not None for r in rows):
        return "n_reached", "concurrency reached  (time-weighted mean)"
    return "n_set", "concurrency set"


def jobs_frontier(rows, theme, out, theme_name) -> list[Path]:
    """What concurrency buys, and — where the run was priced — what it charges.

    Two panels sharing the x-axis, or one where no unit cost was recorded.
    """
    axis, axis_name = jobs_axis(rows)
    pts = [r for r in rows
           if num(r, axis) is not None and num(r, "throughput") is not None]
    if not pts:
        raise Skip(f"needs {axis} and throughput")
    pts.sort(key=lambda r: num(r, axis))
    clean = [r for r in pts if not flag(r, "dominated")]
    dominated = [r for r in pts if flag(r, "dominated")]
    unit, period = unit_of(rows), period_of(rows)
    priced = [r for r in pts if num(r, "usd_per_1m_units") is not None]

    fig, axes = new_figure(2 if priced else 1)
    top, bottom = axes if priced else (axes, None)
    x = [num(r, axis) for r in clean]

    top.plot(x, [num(r, "throughput") for r in clean], color=theme["series"],
             linewidth=LINE_W, marker="o", markersize=MARKER_SZ, zorder=3)
    if bottom is not None:
        cost = [r for r in clean if num(r, "usd_per_1m_units") is not None]
        bottom.plot([num(r, axis) for r in cost],
                    [num(r, "usd_per_1m_units") for r in cost],
                    color=theme["cost"], linewidth=LINE_W, marker="s",
                    markersize=MARKER_SZ, zorder=3)

    # Hollow and off the line, and drawn before the limits are fixed below, or
    # the axis closes over a point that sits outside the clean range.
    for r in dominated:
        hollow(top, num(r, axis), num(r, "throughput"), theme["series"])
        if bottom is not None and num(r, "usd_per_1m_units") is not None:
            hollow(bottom, num(r, axis), num(r, "usd_per_1m_units"),
                   theme["cost"], marker="s")

    panel_label(top, f"{unit}/{period}", theme)
    top.set_ylim(bottom=0)
    headroom(top, top=0.22, right=0.07)
    if bottom is not None:
        panel_label(bottom, f"$/1M {unit}", theme)
        bottom.set_ylim(bottom=0)
        headroom(bottom, top=0.20)
        bottom.yaxis.set_major_formatter(canvas.FuncFormatter(thousands))

    frame = bottom if bottom is not None else top
    axis_label(frame, axis_name)
    style_axis(top, theme, ticks=bottom is None)
    if bottom is not None:
        style_axis(bottom, theme)

    renderer = renderer_for(fig)
    placed_top, placed_bottom = [], []
    for r in pts:
        n_set = num(r, "n_set")
        if n_set is None or axis == "n_set":
            continue
        place_label(top, f"N={n_set:.0f}",
                    (num(r, axis), num(r, "throughput")), theme,
                    renderer, placed_top, colour=theme["secondary"], first=ABOVE)
    for r in dominated:
        if bottom is None or num(r, "usd_per_1m_units") is None:
            continue
        place_label(bottom, "dominated",
                    (num(r, axis), num(r, "usd_per_1m_units")), theme,
                    renderer, placed_bottom, first=BESIDE)
    return [save(fig, out, "frontier-jobs", theme_name)]


def jobs_tradeoff(rows, theme, out, theme_name) -> list[Path]:
    pts = [r for r in rows
           if num(r, "throughput") is not None
           and num(r, "usd_per_1m_units") is not None]
    if not pts:
        raise Skip("needs throughput and usd_per_1m_units on one row")
    pts.sort(key=lambda r: num(r, "throughput"))
    clean = [r for r in pts if not flag(r, "dominated")]
    unit, period = unit_of(rows), period_of(rows)

    fig, ax = new_figure()
    ax.plot([num(r, "throughput") for r in clean],
            [num(r, "usd_per_1m_units") for r in clean],
            color=theme["cost"], linewidth=LINE_W, marker="o",
            markersize=MARKER_SZ, zorder=3)
    for r in (p for p in pts if flag(p, "dominated")):
        hollow(ax, num(r, "throughput"), num(r, "usd_per_1m_units"),
               theme["muted"])

    axis_label(ax, f"{unit}/{period}")
    panel_label(ax, f"$/1M {unit}", theme)
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    headroom(ax, top=0.10, right=0.16)
    ax.yaxis.set_major_formatter(canvas.FuncFormatter(thousands))
    style_axis(ax, theme)

    renderer = renderer_for(fig)
    placed = []
    for r in pts:
        n_set = num(r, "n_set")
        if n_set is None:
            continue
        colour = theme["muted"] if flag(r, "dominated") else theme["secondary"]
        # Beside rather than above: this curve is steep, and directly above a
        # mark is on the next segment of the line.
        place_label(ax, f"N={n_set:.0f}",
                    (num(r, "throughput"), num(r, "usd_per_1m_units")),
                    theme, renderer, placed, colour=colour, first=BESIDE_BELOW)
    return [save(fig, out, "tradeoff-jobs", theme_name)]


def api_frontier(rows, theme, out, theme_name) -> list[Path]:
    """What the window average said, and — where replica counts were recorded —
    what the autoscaler was doing while it said it."""
    pts = [r for r in rows
           if num(r, "offered_rps") is not None
           and num(r, "p95_ms") is not None
           and not flag(r, "excluded")]
    if not pts:
        raise Skip("needs offered_rps and p95_ms on at least one row")
    pts.sort(key=lambda r: num(r, "offered_rps"))

    # Ranked by peak so the busiest tier takes the solid style.
    series = replica_series(header_of(rows))
    series = [s for s in series
              if any(num(r, s[0]) is not None for r in pts)]
    series.sort(key=lambda pair: -max(num(r, pair[0]) or 0 for r in pts))

    fig, axes = new_figure(2, height_ratios=[1.45, 1.0]) if series \
        else new_figure(1)
    top, bottom = axes if series else (axes, None)
    x = [num(r, "offered_rps") for r in pts]

    top.plot(x, [num(r, "p95_ms") for r in pts], color=theme["cost"],
             linewidth=LINE_W, marker="o", markersize=MARKER_SZ, zorder=3,
             label="window average")
    converged = [num(r, "p95_converged_ms") for r in pts]
    if any(v is not None for v in converged):
        top.plot(x, converged, color=theme["series"], linewidth=LINE_W,
                 linestyle=(0, (6, 4)), marker="D", markersize=MARKER_SZ * 0.8,
                 zorder=4, label="once converged")

    # Replicas are an autoscaler output, not a swept axis: step, not line.
    for index, (column, name) in enumerate(series):
        bottom.step(x, [num(r, column) for r in pts], where="post",
                    color=theme["series"], linewidth=LINE_W * 0.7,
                    linestyle=SERIES_STYLES[index % len(SERIES_STYLES)],
                    zorder=3, label=name)

    panel_label(top, "p95 ms", theme)
    top.set_ylim(bottom=0)
    headroom(top, top=0.30)
    if any(v is not None for v in converged):
        legend(top, theme, loc="upper left")
    if bottom is not None:
        panel_label(bottom, "replicas", theme)
        bottom.set_ylim(bottom=0)
        headroom(bottom, top=0.26)
        style_axis(bottom, theme)
        legend(bottom, theme, loc="upper left", ncol=len(series))
    axis_label(bottom if bottom is not None else top, "offered req/s")
    style_axis(top, theme, ticks=bottom is None)

    reference = num(rows[0], "reference_ms")
    if reference:
        top.axhline(reference, color=theme["muted"], linewidth=HAIRLINE,
                    linestyle=(0, (8, 6)))
        # Under its own rule at the right end, deliberately rather than by
        # `place_label`: this labels the rule, not a mark, and the panel's two
        # series are above it — the only thing it must stay clear of.
        label = cell(rows[0], "reference_note") or "reference"
        annotate(top, f"{label}  {reference:,.0f} ms", (x[-1], reference),
                 (0, -LABEL_DY - TYPE_LABEL), theme, ha="right")
    return [save(fig, out, "frontier-api", theme_name)]
