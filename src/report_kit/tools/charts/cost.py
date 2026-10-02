"""Report §4: the split, the floor, the amortization. None of them a rate."""

from __future__ import annotations

import math
from pathlib import Path

from . import canvas
from .canvas import (HAIRLINE, LINE_W, MARKER_SZ, annotate, axis_label,
                     headroom, headroom_log, ink_on, legend, new_figure,
                     note, panel_label, save, style_axis)
from .contract import cell, header_of, num, singular, split_workloads
from .errors import Skip
from .labels import (BESIDE, LABEL_DX, LABEL_DY, place_label, renderer_for,
                     rule_obstacle)

SPLIT_STEPS = 2
SPLIT_ASIDE = "unused_fleet"
SPLIT_AXIS = "n_set"

# Past this much of the x-span, a callout flips to the other side of its rule.
CALLOUT_SIDE = 0.6


def split_segments(pts: list[dict], columns: list[str]) -> list[tuple]:
    """Per-workload columns as stacked segments, ranked by what each costs
    across every row, so the ramp follows magnitude rather than header order.
    Everything past `SPLIT_STEPS` folds into one, because a stack of five is
    five colours nobody holds apart."""
    ranked = sorted(columns, key=lambda c: -sum(num(r, c) or 0.0 for r in pts))
    segments = [(c, [num(r, c) or 0.0 for r in pts]) for c in ranked[:SPLIT_STEPS]]
    rest = ranked[SPLIT_STEPS:]
    if rest:
        segments.append(("other", [sum(num(r, c) or 0.0 for c in rest)
                                   for r in pts]))
    return segments


def jobs_split(rows, theme, out, theme_name) -> list[Path]:
    """Per-workload cost at each step, beside the unused-capacity bar.

    The two bars are not addends, which is why the aside is hatched rather than
    given a hue of its own: it is a different kind of quantity.
    """
    pts = [r for r in rows if num(r, SPLIT_AXIS) is not None]
    if not pts:
        raise Skip(f"needs {SPLIT_AXIS}")
    pts.sort(key=lambda r: num(r, SPLIT_AXIS))
    columns = split_workloads(header_of(rows))
    if not columns:
        raise Skip("needs at least one workload column")

    fig, ax = new_figure()
    positions = list(range(len(pts)))
    width = 0.34
    left = [p - width / 2 - 0.02 for p in positions]
    right = [p + width / 2 + 0.02 for p in positions]

    segments = split_segments(pts, columns)
    bottom = [0.0] * len(pts)
    for step, (key, values) in enumerate(segments):
        ax.bar(left, values, width=width, bottom=bottom,
               color=theme["ramp"][step % len(theme["ramp"])], label=key,
               edgecolor="none", zorder=3)
        bottom = [b + v for b, v in zip(bottom, values)]

    if any(num(r, SPLIT_ASIDE) is not None for r in pts):
        ax.bar(right, [num(r, SPLIT_ASIDE) or 0.0 for r in pts], width=width,
               facecolor=theme["hatch_face"], edgecolor=theme["hatch_edge"],
               hatch="///", linewidth=HAIRLINE, label="unused, fleet-wide",
               zorder=3)

    # The ramp's lightest step is under 3:1 against the surface, so a segment
    # carries its own value rather than relying on the fill.
    tallest = max(range(len(pts)), key=lambda i: segments[0][1][i])
    running = 0.0
    for step, (_key, values) in enumerate(segments):
        mid = running + values[tallest] / 2
        running += values[tallest]
        if values[tallest] < 0.08:
            continue
        annotate(ax, f"${values[tallest]:.2f}", (left[tallest], mid), (0, -12),
                 theme, colour=ink_on(theme["ramp"][step % len(theme["ramp"])]),
                 ha="center")

    smallest = min(columns, key=lambda c: sum(num(r, c) or 0.0 for r in pts))
    totals = [(num(r, smallest) or 0) / (num(r, "workload_total") or 1) * 100
              for r in pts if num(r, smallest) is not None]
    if totals and "workload_total" in header_of(rows):
        note(ax, f"{smallest}: {min(totals):.1f}-{max(totals):.1f}% of workload "
                 f"cost, at every step", (1.0, 0.84), theme, colour=theme["ink"])

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{num(r, SPLIT_AXIS):.0f}" for r in pts])
    axis_label(ax, "N set")
    panel_label(ax, "$ per run, instance-hours", theme)
    headroom(ax, top=0.26)
    style_axis(ax, theme)
    legend(ax, theme, loc="upper center", ncol=len(segments) + 1)
    return [save(fig, out, "split-jobs", theme_name)]

def floor_blocks(rows, theme, out, theme_name) -> list[Path]:
    """One stacked bar: what leaves with the feature, and what does not."""
    by_block = {cell(r, "block").upper(): r for r in rows}
    b = num(by_block.get("B", {}), "usd_per_month")
    a = num(by_block.get("A", {}), "usd_per_month")
    if b is None or a is None:
        raise Skip("needs blocks A and B with usd_per_month")

    fig, ax = new_figure()
    ax.barh([0], [b], height=0.60, color=theme["ramp"][0],
            label="B · dedicated", edgecolor="none", zorder=3)
    ax.barh([0], [a], left=[b], height=0.60, color=theme["ramp"][2],
            label="A · shared", edgecolor="none", zorder=3)

    annotate(ax, f"${b:,.2f}", (b / 2, 0), (0, -12), theme,
             colour=ink_on(theme["ramp"][0]), ha="center")
    annotate(ax, f"${a:,.2f}", (b + a / 2, 0), (0, -12), theme,
             colour=ink_on(theme["ramp"][2]), ha="center")
    note(ax, f"C · total  ${b + a:,.2f}/month", (1.0, 1.0), theme,
         colour=theme["ink"])

    ax.set_yticks([])
    ax.set_ylim(-0.85, 0.85)
    ax.set_xlim(0, (b + a) * 1.04)
    axis_label(ax, "$/month")
    ax.spines["left"].set_visible(False)
    style_axis(ax, theme, grid_axis="x")
    legend(ax, theme, loc="lower left", ncol=2)
    return [save(fig, out, "floor-blocks", theme_name)]


def crossover_callout(ax, crossover: float, unit: str, theme: dict, renderer):
    """Names the 50%-floor volume at the top of its rule, on the side with
    room. Returns its box, so the point labels can steer around it."""
    lo, hi = (math.log10(v) for v in ax.get_xlim())
    on_right = (math.log10(crossover) - lo) / (hi - lo) > CALLOUT_SIDE
    ha, dx = ("right", -LABEL_DX) if on_right else ("left", LABEL_DX)
    ann = annotate(ax, f"50% floor share\n{crossover:,.0f} {unit}/month",
                   (crossover, ax.get_ylim()[1]), (dx, -LABEL_DY - 2), theme,
                   ha=ha)
    return ann.get_window_extent(renderer)


def amortization_one(rows, theme, out, theme_name, unit: str) -> Path:
    pts = [r for r in rows
           if cell(r, "unit") == unit
           and num(r, "volume") is not None
           and num(r, "effective_usd_per_unit") is not None]
    if not pts:
        raise Skip(f"no rows for unit={unit}")
    pts.sort(key=lambda r: num(r, "volume"))

    fig, ax = new_figure()
    ax.plot([num(r, "volume") for r in pts],
            [num(r, "effective_usd_per_unit") for r in pts],
            color=theme["cost"], linewidth=LINE_W, marker="o",
            markersize=MARKER_SZ, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    headroom_log(ax, top=2.4, right=1.9, bottom=1.35)

    axis_label(ax, f"{unit} per month")
    panel_label(ax, f"effective $/{singular(unit)}", theme)
    ax.yaxis.set_major_formatter(canvas.LogFormatterSciNotation())
    style_axis(ax, theme)

    crossover = num(pts[0], "crossover_volume")
    if crossover:
        # The crossover can sit far to the right of every swept volume.
        # Extending the axis to reach it is the point: it shows how far off the
        # tested range the break-even actually is.
        if crossover > ax.get_xlim()[1]:
            ax.set_xlim(ax.get_xlim()[0], crossover * 1.6)
        ax.axvline(crossover, color=theme["muted"], linewidth=HAIRLINE,
                   linestyle=(0, (8, 6)))

    renderer = renderer_for(fig)
    obstacles, soft = [], []
    if crossover:
        soft.append(rule_obstacle(ax, crossover, renderer))
        obstacles.append(crossover_callout(ax, crossover, unit, theme, renderer))

    for r in pts:
        share = num(r, "floor_share_pct")
        if share is None:
            continue
        place_label(ax, f"{share:g}% floor",
                    (num(r, "volume"), num(r, "effective_usd_per_unit")),
                    theme, renderer, obstacles, colour=theme["secondary"],
                    soft=soft, first=BESIDE)
    return save(fig, out, f"amortization-{unit}", theme_name)


def amortization(rows, theme, out, theme_name) -> list[Path]:
    units = sorted({cell(r, "unit") for r in rows if cell(r, "unit")})
    if not units:
        raise Skip("needs a unit column")
    return [amortization_one(rows, theme, out, theme_name, u) for u in units]
