from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from .clock import utcnow
from .constants import WARN


def poll_until(check: Callable[[], bool], *, poll_seconds: float,
               max_wait_seconds: float,
               on_error: Callable[[RuntimeError], None] | None = None) -> bool:
    """Call check() every poll_seconds until it returns truthy or
    max_wait_seconds elapses. Returns whichever happened first.

    check() owns the state it gathers and any progress line it prints; this
    function owns only the timeout arithmetic and the tolerate-one-bad-poll
    retry. A RuntimeError from check() is caught and treated as "not yet"
    rather than aborting the wait: one failed kubectl call in an hour-long
    watch is noise, not an answer.

    Not a fit for a loop tracking several concerns at once — interrupt
    detection, keeping a port-forward alive, conditions that close at
    different times. That shape stays a hand-written loop rather than being
    forced through a single check() callable."""
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        try:
            if check():
                return True
        except RuntimeError as e:
            (on_error or _default_on_error)(e)
        time.sleep(poll_seconds)
    return False


def wait_until_stable(check: Callable[[], bool], *, hold_seconds: float,
                      poll_seconds: float, max_wait_seconds: float,
                      on_tick: Callable[[bool, float], None] | None = None,
                      on_error: Callable[[RuntimeError], None] | None = None,
                      ) -> datetime | None:
    """Wait until check() has been continuously true for hold_seconds.

    Returns the instant the condition *first* became true (UTC), or None if
    max_wait_seconds ran out first. The hold timer resets on any false or
    failed poll — that reset is the entire point of this function.

    Closing a measurement window on "the condition is true right now" is the
    classic way to record a garbage point: a queue reads zero for one poll
    while messages are still in flight, a deployment touches its floor
    between two scaling decisions, and the window closes mid-run. Requiring
    the condition to hold costs one buffer period and removes that whole
    class of bad data.

    Why it returns the *start* of the hold rather than a bool: the caller
    decides what the buffer means. Scale-in is caused by the load and is
    usually billed to the point, so t_end is often "now"; the confirmation
    buffer after everything settled usually isn't part of the phenomenon,
    so t_end can be this return value instead. Both readings are defensible,
    neither belongs in this function — pick one in the runner and say which
    in the point record.

    `on_tick(ok, held_seconds)` fires after every poll, for a progress line;
    held_seconds is 0.0 whenever the condition is not currently holding.
    """
    if hold_seconds >= max_wait_seconds:
        raise ValueError(
            f"hold_seconds ({hold_seconds}) >= max_wait_seconds "
            f"({max_wait_seconds}): the hold can never complete inside the "
            f"timeout, so this would always report a timeout no matter how "
            f"healthy the system is")

    deadline = time.monotonic() + max_wait_seconds
    stable_monotonic: float | None = None
    stable_at: datetime | None = None

    while time.monotonic() < deadline:
        try:
            ok = bool(check())
        except RuntimeError as e:
            (on_error or _default_on_error)(e)
            ok = False  # a failed poll is not evidence of stability

        now = time.monotonic()
        if ok:
            if stable_monotonic is None:
                stable_monotonic, stable_at = now, utcnow()
            held = now - stable_monotonic
        else:
            stable_monotonic, stable_at = None, None
            held = 0.0

        if on_tick:
            on_tick(ok, held)
        if ok and held >= hold_seconds:
            return stable_at

        time.sleep(poll_seconds)

    return None


def _default_on_error(e: RuntimeError) -> None:
    print(f"{WARN} poll failed ({e}) — retrying")
