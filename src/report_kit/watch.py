"""Watching a point's window close: on a condition that has held, never on a
system that was not yet busy, with the peak of every reading and the instant
each named condition first held kept for the point record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from . import poll
from .clock import hms, utcnow
from .constants import ARROW, WARN
from .window import Window

if TYPE_CHECKING:
    from .point import Point

State = dict
Condition = Callable[[State], bool]


@dataclass(frozen=True)
class Watched:
    """`window` is None when it never closed; `events` are epoch seconds."""

    window: Window | None
    state: State
    peaks: dict[str, float]
    events: dict[str, float]


def watch(point: "Point", read_state: Callable[[], State], at_rest: Condition,
          start: datetime, *, require_busy: bool | None = None,
          events: dict[str, Condition] | None = None,
          keep_alive: Callable[[], list[str]] | None = None,
          hold_seconds: float | None = None, label: str = "the window") -> Watched:
    """`require_busy` defaults to the plan's load: a background load starts with
    the watch, and an untouched system already reads at rest, so the window
    may only close on a system seen busy first. `events` name conditions
    whose first instant — once the system was busy — the record keeps."""
    if require_busy is None:
        require_busy = point.plan.load == "background"
    seen_busy = not require_busy
    state: State = {}
    peaks: dict[str, float] = {}
    instants: dict[str, float] = {}
    hold = point.plan.hold_seconds if hold_seconds is None else hold_seconds

    def closed() -> bool:
        nonlocal seen_busy
        for notice in keep_alive() if keep_alive else []:
            print(f"{WARN} {notice}")
        state.clear()
        state.update(read_state())
        raise_peaks(peaks, readings(state))
        rest = at_rest(state)
        seen_busy = seen_busy or not rest
        if seen_busy:
            mark(instants, events or {}, state)
        return seen_busy and rest

    print()
    print(f"{ARROW} watching {label} close — hold {hold:g}s, poll "
          f"{point.env.poll_seconds:g}s, timeout {hms(point.env.max_wait_seconds)}")
    settled = poll.wait_until_stable(
        closed, hold_seconds=hold, poll_seconds=point.env.poll_seconds,
        max_wait_seconds=point.env.max_wait_seconds,
        on_tick=lambda ok, held: print(f"    {shown(state)}"
                                       f"{f' · held {int(held)}s/{hold:g}s' if ok else ''}"))
    window = None if settled is None else Window(start, settled)
    return Watched(window, dict(state), peaks, instants)


def readings(state: State, prefix: str = "") -> dict[str, float]:
    """Every number in the state, nested keys joined with dots."""
    found: dict[str, float] = {}
    for key, value in state.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            found.update(readings(value, f"{name}."))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            found[name] = float(value)
    return found


def raise_peaks(peaks: dict[str, float], current: dict[str, float]) -> None:
    for name, value in current.items():
        peaks[name] = max(peaks.get(name, value), value)


def mark(instants: dict[str, float], events: dict[str, Condition], state: State) -> None:
    for name, holds in events.items():
        if name not in instants and holds(state):
            instants[name] = utcnow().timestamp()


def shown(state: State) -> str:
    return " ".join(f"{name}={value:g}" for name, value in readings(state).items())
