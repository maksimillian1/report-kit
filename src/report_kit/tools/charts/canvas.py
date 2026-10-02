"""Size, type, palette, and the helpers that put an axis or a label on a figure.

`load_backend()` binds matplotlib into four module globals, so every other
module must reach them as `canvas.plt`, `canvas.Bbox` — a `from .canvas import
plt` captures `None` at import time and fails at the first draw. Same rule
`API.md` states for `shell.sh_json`. Why the import is deferred at all, and the
surface the sizes here serve: `charts.md`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .errors import ChartError


# The SVG backend writes user units as points, so 1620 x 1000 units makes one
# unit one pixel on an 1800px slide canvas.
CANVAS_W, CANVAS_H = 1620, 1000
DPI = 72

TYPE_BODY = 34
TYPE_AXIS = 38
TYPE_LABEL = 34

# Lists, not strings: matplotlib writes them out as a CSS font stack.
FONT_SANS = ["Poppins", "sans-serif"]
FONT_MONO = ["IBM Plex Mono", "monospace"]

GRID_ALPHA = 0.35
LINE_W = 4.0
MARKER_SZ = 16
HAIRLINE = 1.6
GUTTER_IN = 16 / 72
NOTE_PAD = 16

# `ramp` runs away from its own surface, so its steps are ordered differently
# per theme rather than being one palette with a swapped ink.
THEMES = {
    "light": {
        "ink": "#0b1320",
        "secondary": "#1c3f60",
        "rule": "#6c8aa8",
        "series": "#3d85c6",
        "cost": "#c1272d",
        "muted": "#6c8aa8",
        "ramp": ["#17364f", "#3d85c6", "#afc1d0"],
        "hatch_face": "#ffffff",
        "hatch_edge": "#6c8aa8",
    },
    "navy": {
        "ink": "#ffffff",
        "secondary": "#afc1d0",
        "rule": "#6c8aa8",
        "series": "#3d85c6",
        "cost": "#ffd966",
        "muted": "#afc1d0",
        "ramp": ["#3d85c6", "#afc1d0", "#f3f6fa"],
        "hatch_face": "#1c3f60",
        "hatch_edge": "#afc1d0",
    },
}

plt = None
FuncFormatter = LogFormatterSciNotation = Bbox = None


def load_backend() -> None:
    global plt, FuncFormatter, LogFormatterSciNotation, Bbox
    if plt is not None:
        return
    try:
        import matplotlib
    except ModuleNotFoundError as exc:
        raise ChartError('rendering needs matplotlib — pip install '
                         '"report-kit[charts]"') from exc
    matplotlib.use("Agg")
    import matplotlib.pyplot
    from matplotlib.ticker import FuncFormatter as _FF
    from matplotlib.ticker import LogFormatterSciNotation as _LF
    from matplotlib.transforms import Bbox as _Bbox

    # The named fonts are resolved by whatever opens the SVG, so this machine
    # not having them is expected rather than a warning.
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    plt = matplotlib.pyplot
    FuncFormatter, LogFormatterSciNotation, Bbox = _FF, _LF, _Bbox


def configure(theme: dict) -> None:
    plt.rcParams.update(
        {
            "svg.fonttype": "none",          # keep text as text
            "font.family": "sans-serif",
            "font.sans-serif": FONT_SANS + ["DejaVu Sans"],
            "text.color": theme["ink"],
            "axes.edgecolor": theme["rule"],
            "axes.labelcolor": theme["ink"],
            "xtick.color": theme["ink"],
            "ytick.color": theme["ink"],
            "axes.linewidth": HAIRLINE,
            "figure.facecolor": "none",
            "axes.facecolor": "none",
            "savefig.facecolor": "none",
            "savefig.transparent": True,
            "hatch.linewidth": 2.0,
        }
    )


def new_figure(rows: int = 1, height_ratios=None):
    # Every chart starts here, so this is where the backend is guaranteed to be
    # loaded. Without it a draw function called directly by a script fails on a
    # None global instead of saying what is missing.
    load_backend()
    fig, axes = plt.subplots(
        rows, 1, figsize=(CANVAS_W / DPI, CANVAS_H / DPI), dpi=DPI,
        layout="constrained", sharex=(rows > 1),
        gridspec_kw={"height_ratios": height_ratios} if height_ratios else None,
    )
    fig.get_layout_engine().set(w_pad=GUTTER_IN, h_pad=GUTTER_IN)
    return fig, axes


def style_axis(ax, theme: dict, grid_axis: str = "y", ticks: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=TYPE_BODY, length=10, width=HAIRLINE, pad=12)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(FONT_MONO)
        label.set_fontsize(TYPE_BODY)
    if not ticks:
        ax.tick_params(axis="x", length=0)
    ax.grid(True, axis=grid_axis, color=theme["rule"], alpha=GRID_ALPHA,
            linewidth=1.0)
    ax.set_axisbelow(True)


def headroom(ax, top: float = 0.0, right: float = 0.0) -> None:
    """Grow the limits so labels have room inside the frame.

    Fixes the limits as a side effect, so everything plotted has to be on the
    axes before this runs or the axis closes over it.
    """
    if top:
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo, hi + (hi - lo) * top)
    if right:
        lo, hi = ax.get_xlim()
        ax.set_xlim(lo, hi + (hi - lo) * right)


def headroom_log(ax, top: float = 1.0, right: float = 1.0,
                 bottom: float = 1.0) -> None:
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo / bottom, hi * top)
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo, hi * right)


def annotate(ax, text: str, xy, offset, theme: dict, colour: str | None = None,
             ha: str = "left"):
    return ax.annotate(text, xy=xy, xytext=offset, textcoords="offset points",
                       ha=ha, fontsize=TYPE_LABEL, fontfamily=FONT_MONO,
                       color=colour or theme["muted"])


def note(ax, text: str, xy_axes, theme: dict, colour: str | None = None,
         ha: str = "right", va: str = "top", pad: float = NOTE_PAD):
    """A callout pinned to the axes, inset from its anchor so that an anchor on
    the frame does not put text on the frame."""
    dx = {"right": -pad, "left": pad}.get(ha, 0.0)
    dy = {"top": -pad, "bottom": pad}.get(va, 0.0)
    return ax.annotate(text, xy=xy_axes, xycoords="axes fraction",
                       xytext=(dx, dy), textcoords="offset points", ha=ha,
                       va=va, fontsize=TYPE_LABEL, fontfamily=FONT_MONO,
                       color=colour or theme["muted"])


def legend(ax, theme: dict, loc: str = "upper left", ncol: int = 1):
    leg = ax.legend(loc=loc, ncol=ncol, frameon=False, fontsize=TYPE_BODY,
                    handlelength=1.6, borderaxespad=0.8, labelspacing=0.5,
                    columnspacing=1.6)
    for text in leg.get_texts():
        text.set_fontfamily(FONT_MONO)
        text.set_color(theme["ink"])
    return leg


def panel_label(ax, text: str, theme: dict) -> None:
    ax.set_ylabel(text, fontsize=TYPE_AXIS, fontfamily=FONT_SANS,
                  color=theme["ink"], labelpad=18)


def axis_label(ax, text: str) -> None:
    ax.set_xlabel(text, fontsize=TYPE_AXIS, fontfamily=FONT_SANS, labelpad=18)


def hollow(ax, x, y, colour: str, marker: str = "o") -> None:
    """A mark drawn off the line: on the chart, and not part of the series."""
    ax.plot(x, y, marker=marker, markersize=MARKER_SZ, markerfacecolor="none",
            markeredgecolor=colour, markeredgewidth=HAIRLINE * 1.6, zorder=3)


def thousands(value, _pos):
    return f"{value:,.0f}"


INK_ON_DARK, INK_ON_LIGHT = "#ffffff", "#0b1320"


def ink_on(fill: str) -> str:
    r, g, b = (int(fill[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
           for c in (r, g, b)]
    luminance = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return INK_ON_LIGHT if luminance > 0.4 else INK_ON_DARK


def save(fig, out: Path, name: str, theme_name: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    suffix = "" if theme_name == "light" else f"-{theme_name}"
    path = out / f"{name}{suffix}.svg"
    # No bbox_inches="tight": cropping would change the viewBox and break the
    # one-unit-is-one-slide-pixel contract the type sizes depend on.
    fig.savefig(path, format="svg")
    plt.close(fig)
    return path
