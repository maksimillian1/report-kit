"""The four shapes a chart can be. Each reads a `Table` and draws nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import canvas, table
from .canvas import (HAIRLINE, LINE_W, MARKER_SZ, annotate, axis_label,
                     headroom, headroom_log, ink_on, legend, new_figure, note,
                     panel_label, save, style_axis)
from .errors import Skip
from .labels import ABOVE, place_label, renderer_for, rule_obstacle

BAR_W = 0.34
STEP_STYLES = ("-", (0, (6, 4)), (0, (2, 3)))
MIN_LABELLED = 0.08
PANEL_INK = ("series", "cost")
LEGEND_COLUMNS = 2
DASHED = (0, (8, 6))
GAP = float("nan")


@dataclass(frozen=True)
class Marks:
    rule: tuple | None = None
    mark_x: tuple | None = None
    join: bool = True


NO_MARKS = Marks()


def rows_with(values) -> tuple:
    return tuple(i for i, v in enumerate(values) if v is not None)


def ramp(theme: dict, step: int) -> str:
    return theme["ramp"][step % len(theme["ramp"])]


def axis_title(column: table.Column) -> str:
    return (column.name if column.unit == column.name
            else f"{column.name}  ({column.unit})")


def caption(value: float, text: str) -> str:
    return f"{text}  {value:,.0f}" if text else f"{value:,.0f}"


def draw_rule(ax, rule, theme: dict) -> None:
    if rule is None:
        return
    value, text = rule
    ax.axhline(value, color=theme["muted"], linewidth=HAIRLINE,
               linestyle=DASHED)
    lo, hi = ax.get_xlim()
    annotate(ax, caption(value, text), (hi, value), (0, -52), theme, ha="right")


def draw_mark_x(frames, mark, theme: dict) -> None:
    if mark is None:
        return
    value, text = mark
    for frame in frames:
        frame.axvline(value, color=theme["muted"], linewidth=HAIRLINE,
                      linestyle=DASHED, zorder=2)
    lo, hi = frames[0].get_ylim()
    annotate(frames[0], caption(value, text), (value, hi), (14, -44), theme)


def plot_panel(frame, group, ink: str, xs, present, theme: dict,
               marks: Marks, log_x: bool, log_y: bool) -> None:
    for index, column in enumerate(group.columns):
        ys = [GAP if column.values[i] is None else column.values[i]
              for i in present]
        style = STEP_STYLES[index % len(STEP_STYLES)]
        frame.plot(xs, ys, color=ink, linewidth=LINE_W,
                   linestyle=style if marks.join else "none",
                   marker="o", markersize=MARKER_SZ, zorder=3,
                   label=column.name if len(group.columns) > 1 else None)
    panel_label(frame, group.title, theme)
    if log_x:
        frame.set_xscale("log")
    if log_y:
        frame.set_yscale("log")
    else:
        frame.set_ylim(bottom=0)
        frame.yaxis.set_major_formatter(canvas.FuncFormatter(canvas.thousands))
    if len(group.columns) > 1:
        legend(frame, theme)


def label_points(fig, frame, data: table.Table, column: table.Column,
                 theme: dict, marks: Marks) -> None:
    renderer = renderer_for(fig)
    soft = ([rule_obstacle(frame, marks.mark_x[0], renderer)]
            if marks.mark_x else [])
    placed = []
    for row in rows_with(column.values):
        text = data.label_at(row)
        if text and data.x.values[row] is not None:
            place_label(frame, text, (data.x.values[row], column.values[row]),
                        theme, renderer, placed, colour=theme["secondary"],
                        soft=soft, first=ABOVE)


def line(data: table.Table, theme: dict, out: Path, theme_name: str,
         marks: Marks = NO_MARKS) -> list[Path]:
    data = table.with_axis(data)
    log_x, log_y = table.log_axes(data)
    panels = data.panels + data.aside
    fig, axes = new_figure(len(panels))
    frames = axes if len(panels) > 1 else (axes,)
    present = rows_with(data.x.values)
    xs = [data.x.values[i] for i in present]

    for panel, (frame, group) in enumerate(zip(frames, panels)):
        ink = (theme[PANEL_INK[panel]] if panel < len(PANEL_INK)
               else ramp(theme, panel))
        plot_panel(frame, group, ink, xs, present, theme, marks, log_x, log_y)

    last = frames[-1]
    for frame in frames:
        (headroom_log(frame, top=2.0, right=1.6) if log_x
         else headroom(frame, top=0.26, right=0.07))
        style_axis(frame, theme, ticks=frame is last)
    axis_label(last, axis_title(data.x))
    draw_rule(frames[0], marks.rule, theme)
    draw_mark_x(frames, marks.mark_x, theme)
    label_points(fig, frames[0], data, panels[0].columns[0], theme, marks)
    return [save(fig, out, data.path.stem, theme_name)]


def fold(columns, steps: int) -> list:
    """Keep the largest `steps - 1` columns and fold the rest into one.

    More segments than the ramp has steps means two of them share a colour, so
    the tail becomes a single `other` rather than a stack nobody can read.
    """
    ordered = sorted(columns, key=lambda c: -sum(v or 0 for v in c.values))
    if len(ordered) <= steps:
        return ordered
    kept, tail = ordered[:steps - 1], ordered[steps - 1:]
    merged = tuple(sum(c.values[i] or 0 for c in tail)
                   for i in range(len(tail[0].values)))
    return kept + [table.Column("other", tail[0].unit, merged)]


def bars(data: table.Table, theme: dict, out: Path, theme_name: str,
         marks: Marks = NO_MARKS) -> list[Path]:
    if not data.labels:
        data = table.with_axis(data)
    ticks = ([data.label_at(i) for i in range(data.rows)] if data.labels
             else [f"{v:g}" for v in data.x.values])

    fig, ax = new_figure()
    at = list(range(data.rows))
    paired = bool(data.aside)
    width = BAR_W if paired else BAR_W * 1.6
    left = [p - BAR_W / 2 - 0.02 for p in at] if paired else at

    for side, groups in ((left, data.panels),
                         ([p + BAR_W / 2 + 0.02 for p in at], data.aside)):
        for group in groups:
            ordered = fold(group.columns, len(theme["ramp"]))
            bottom = [0.0] * data.rows
            for step, column in enumerate(ordered):
                values = [v or 0.0 for v in column.values]
                fill = (dict(facecolor=theme["hatch_face"], hatch="///",
                             edgecolor=theme["hatch_edge"], linewidth=HAIRLINE)
                        if group.aside else dict(color=ramp(theme, step)))
                ax.bar(side, values, width=width, bottom=bottom,
                       label=column.name, zorder=3, **fill)
                bottom = [b + v for b, v in zip(bottom, values)]
            if not group.aside:
                label_tallest(ax, side, ordered, theme)

    ax.set_xticks(at)
    ax.set_xticklabels(ticks)
    axis_label(ax, data.labels[0].name if data.labels else axis_title(data.x))
    panel_label(ax, data.panels[0].title if data.panels else "", theme)
    headroom(ax, top=0.26)
    style_axis(ax, theme)
    legend(ax, theme, loc="upper center",
           ncol=min(len(theme["ramp"]) + len(data.aside), 5))
    return [save(fig, out, data.path.stem, theme_name)]


def label_tallest(ax, at, ordered, theme: dict) -> None:
    """The ramp's lightest step is under 3:1 against the surface, so the tallest
    bar carries its own numbers."""
    totals = [sum(c.values[i] or 0 for c in ordered) for i in range(len(at))]
    tall = max(range(len(at)), key=lambda i: totals[i])
    running = 0.0
    for step, column in enumerate(ordered):
        value = column.values[tall] or 0.0
        mid, running = running + value / 2, running + value
        if value >= MIN_LABELLED:
            annotate(ax, f"{value:,.2f}", (at[tall], mid), (0, -12), theme,
                     colour=ink_on(ramp(theme, step)), ha="center")


def parts(data: table.Table, theme: dict, out: Path, theme_name: str,
          marks: Marks = NO_MARKS) -> list[Path]:
    column = data.series[0]
    rows = rows_with(column.values)
    if not rows:
        raise Skip(f"{column.name} has no value to divide")
    pieces = fold([table.Column(data.label_at(i), column.unit,
                                (column.values[i],)) for i in rows],
                  len(theme["ramp"]))
    total = sum(piece.values[0] for piece in pieces)

    fig, ax = new_figure()
    left = 0.0
    for step, piece in enumerate(pieces):
        value = piece.values[0]
        ax.barh([0], [value], left=[left], height=0.60, color=ramp(theme, step),
                label=piece.name, edgecolor="none", zorder=3)
        if value / total > MIN_LABELLED:
            annotate(ax, f"{value:,.2f}", (left + value / 2, 0), (0, -12), theme,
                     colour=ink_on(ramp(theme, step)), ha="center")
        left += value
    note(ax, f"total  {total:,.2f} {column.unit}", (1.0, 1.0), theme,
         colour=theme["ink"])

    ax.set_yticks([])
    ax.set_ylim(-0.85, 0.85)
    ax.set_xlim(0, total * 1.04)
    axis_label(ax, column.unit)
    ax.spines["left"].set_visible(False)
    style_axis(ax, theme, grid_axis="x")
    legend(ax, theme, loc="lower left", ncol=min(len(pieces), LEGEND_COLUMNS))
    return [save(fig, out, data.path.stem, theme_name)]


def waterfall(data: table.Table, theme: dict, out: Path, theme_name: str,
              marks: Marks = NO_MARKS) -> list[Path]:
    """Ordered steps, each starting where the last ended.

    A row restating the running total is drawn from zero and resets it, which is
    how the format carries a subtotal without a column for one.
    """
    column = data.series[0]
    marks = table.subtotals(column.values)
    rows = rows_with(column.values)
    if not rows:
        raise Skip(f"{column.name} has no value to bridge")

    fig, ax = new_figure()
    running = 0.0
    for row in rows:
        value = column.values[row]
        if marks[row]:
            ax.bar([row], [value], width=BAR_W * 1.6, color=ramp(theme, 0),
                   edgecolor="none", zorder=3)
            top, running = value, value
        else:
            ax.bar([row], [value], width=BAR_W * 1.6, bottom=[running],
                   color=theme["cost"] if value < 0 else ramp(theme, 1),
                   edgecolor="none", zorder=3)
            top = running + value
            ax.plot([row - BAR_W, row + BAR_W + 1], [top, top],
                    color=theme["rule"], linewidth=HAIRLINE, zorder=2)
            running = top
        down = not marks[row] and value < 0
        annotate(ax, f"{value:,.4g}" if marks[row] else f"{value:+,.4g}",
                 (row, min(top, running) if down else max(top, running)),
                 (0, -46 if down else 14), theme,
                 colour=theme["ink"] if marks[row] else theme["secondary"],
                 ha="center")

    ax.set_xticks(list(rows))
    ax.set_xticklabels([data.label_at(i) for i in rows], rotation=20, ha="right")
    panel_label(ax, column.unit, theme)
    headroom(ax, top=0.18)
    style_axis(ax, theme)
    return [save(fig, out, data.path.stem, theme_name)]


KINDS = {"line": line, "bars": bars, "parts": parts, "waterfall": waterfall}
NO_AXIS = ("parts", "waterfall")
MARKED = ("line",)
