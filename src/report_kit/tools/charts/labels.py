"""Where a label goes, decided by measuring rather than by a fixed offset.

An annotation is offset in points, which the data limits know nothing about, so
a fixed offset puts a label off the canvas or on top of its neighbour. See
`charts.md` for what this guarantees a reader.
"""

from __future__ import annotations

from . import canvas
from .canvas import TYPE_LABEL, annotate


# Rows: above the mark, below it, then one and two rows higher, so crowded
# marks stack their labels instead of overprinting.
LABEL_DX, LABEL_DY = 18, 18
LABEL_LINE = TYPE_LABEL + 10
LABEL_ROWS = (LABEL_DY, -LABEL_DY - TYPE_LABEL,
              LABEL_DY + LABEL_LINE, LABEL_DY + 2 * LABEL_LINE)
LABEL_SIDES = ((LABEL_DX, "left"), (-LABEL_DX, "right"), (0, "center"))
LABEL_CANDIDATES = tuple(
    (dx, dy, ha)
    for dy in LABEL_ROWS
    for dx, ha in LABEL_SIDES
)

ABOVE = (0, LABEL_DY, "center")
BESIDE = (LABEL_DX, LABEL_DY, "left")
BESIDE_BELOW = (LABEL_DX, -LABEL_DY, "left")
RULE_HALF_W = 12


def renderer_for(fig):
    """Text can only be measured once the layout engine has run."""
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def within(outer, inner) -> bool:
    return (inner.x0 >= outer.x0 and inner.x1 <= outer.x1
            and inner.y0 >= outer.y0 and inner.y1 <= outer.y1)


def rule_obstacle(ax, x_data: float, renderer):
    frame = ax.get_window_extent(renderer)
    x = ax.transData.transform((x_data, ax.get_ylim()[0]))[0]
    return canvas.Bbox.from_extents(x - RULE_HALF_W, frame.y0, x + RULE_HALF_W,
                             frame.y1)


def measure_candidates(ax, text: str, xy, theme: dict, colour, renderer,
                       first=None) -> list:
    """Every candidate placement as (spec, box). Each one is drawn to measure it,
    because matplotlib reports a text extent only for an attached artist."""
    measured = []
    order = LABEL_CANDIDATES if first is None else (first,) + LABEL_CANDIDATES
    for dx, dy, ha in order:
        ann = annotate(ax, text, xy, (dx, dy), theme, colour=colour, ha=ha)
        measured.append(((dx, dy, ha), ann.get_window_extent(renderer)))
        ann.remove()
    return measured


def place_label(ax, text: str, xy, theme: dict, renderer, obstacles: list,
                colour: str | None = None, soft=(), first=None) -> None:
    """Annotate one mark in the first clear position, and record where it went.

    Two passes: the second drops the `soft` obstacles, because a label crossing
    a hairline rule reads and two labels in one spot do not. A label is never
    dropped — the fallback keeps one in a tight corner rather than none.
    """
    frame = ax.get_window_extent(renderer)
    measured = measure_candidates(ax, text, xy, theme, colour, renderer, first)
    inside = [pair for pair in measured if within(frame, pair[1])]
    for avoid in (list(obstacles) + list(soft), list(obstacles)):
        for spec, box in inside:
            if not any(box.overlaps(other) for other in avoid):
                return commit_label(ax, text, xy, spec, theme, colour,
                                    obstacles, box)
    spec, box = inside[0] if inside else measured[0]
    commit_label(ax, text, xy, spec, theme, colour, obstacles, box)


def commit_label(ax, text: str, xy, spec, theme: dict, colour,
                 obstacles: list, box) -> None:
    dx, dy, ha = spec
    obstacles.append(box)
    annotate(ax, text, xy, (dx, dy), theme, colour=colour, ha=ha)
