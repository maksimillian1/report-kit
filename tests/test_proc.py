"""A background load's instants: when it finished is when the process exited,
not when someone next looked.

    pytest tests/test_proc.py
"""

from __future__ import annotations

import sys
import time

from report_kit.proc import Background


def test_a_background_load_finishes_when_it_exits_not_when_it_is_polled(tmp_path):
    with Background([sys.executable, "-c", "pass"], tmp_path / "load.log") as load:
        time.sleep(1.5)
        polled = load.poll()
        looked = time.time()
    assert polled == 0
    assert looked - load.finished_at.timestamp() > 1.0
