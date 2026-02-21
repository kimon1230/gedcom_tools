import io
import os
import threading
from unittest.mock import patch

import pytest

from gedcom_tools.progress import Colors, PhaseTracker, Spinner, _NullSpinner


def _controlled_wait(max_ticks):
    """Return a wait function that allows max_ticks iterations then stops."""
    call_count = 0

    def wait(timeout=None):
        nonlocal call_count
        call_count += 1
        return call_count > max_ticks

    return wait


def _make_tty_stream():
    stream = io.StringIO()
    stream.isatty = lambda: True
    return stream


@pytest.fixture(autouse=True)
def _no_leaked_spinner_threads():
    yield
    leaked = [t for t in threading.enumerate() if t.name == "spinner-animate"]
    assert not leaked, f"Spinner thread leaked: {leaked}"


class TestColors:
    def test_colors_disabled_when_no_stream(self):
        colors = Colors(stream=None)
        assert not colors.enabled
        assert colors.cyan == ""
        assert colors.reset == ""

    def test_colors_disabled_when_force_disable(self):
        stream = io.StringIO()
        colors = Colors(stream=stream, force_disable=True)
        assert not colors.enabled

    def test_colors_disabled_when_no_color_env(self):
        stream = io.StringIO()
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            colors = Colors(stream=stream)
            assert not colors.enabled

    def test_colors_disabled_for_non_tty(self):
        stream = io.StringIO()
        colors = Colors(stream=stream)
        assert not colors.enabled

    def test_colors_enabled_for_tty(self):
        stream = _make_tty_stream()
        colors = Colors(stream=stream)
        assert colors.enabled
        assert colors.cyan == "\033[36m"
        assert colors.green == "\033[32m"
        assert colors.red == "\033[31m"
        assert colors.yellow == "\033[33m"
        assert colors.dim == "\033[2m"
        assert colors.reset == "\033[0m"


class TestSpinner:
    def test_spinner_non_tty_no_animation(self):
        stream = io.StringIO()
        with Spinner("Testing...", stream=stream) as s:
            s.update()
            s.update()
        output = stream.getvalue()
        assert "✓" in output
        assert "Testing..." in output
        assert "\r" not in output

    def test_spinner_tty_has_animation(self):
        stream = _make_tty_stream()
        s = Spinner("Testing...", stream=stream)
        s._stop_event.wait = _controlled_wait(5)
        try:
            s.start()
            if s._thread is not None:
                s._thread.join()
        finally:
            s.stop()
        output = stream.getvalue()
        braille_in_output = [c for c in output if c in Spinner.FRAMES]
        assert len(braille_in_output) >= 2

    def test_spinner_success_shows_checkmark(self):
        stream = io.StringIO()
        with Spinner("Testing...", stream=stream):
            pass
        output = stream.getvalue()
        assert "✓" in output

    def test_spinner_failure_shows_x(self):
        stream = io.StringIO()
        spinner = Spinner("Testing...", stream=stream)
        spinner.start()
        spinner.stop(success=False)
        output = stream.getvalue()
        assert "✗" in output

    def test_spinner_exception_shows_failure(self):
        stream = io.StringIO()
        with pytest.raises(ValueError):
            with Spinner("Testing...", stream=stream):
                raise ValueError("boom")
        output = stream.getvalue()
        assert "✗" in output

    def test_spinner_no_color_flag(self):
        stream = _make_tty_stream()
        s = Spinner("Testing...", stream=stream, no_color=True)
        s._stop_event.wait = _controlled_wait(2)
        try:
            s.start()
            if s._thread is not None:
                s._thread.join()
        finally:
            s.stop()
        output = stream.getvalue()
        assert "\033[36m" not in output  # cyan
        assert "\033[32m" not in output  # green
        assert "\033[31m" not in output  # red
        assert "\033[0m" not in output  # reset

    def test_spinner_manual_start_stop(self):
        stream = io.StringIO()
        s = Spinner("Manual test", stream=stream)
        s.start()
        s.update("suffix")
        s.stop()
        output = stream.getvalue()
        assert "✓" in output

    def test_spinner_update_without_start(self):
        stream = io.StringIO()
        s = Spinner("Not started", stream=stream)
        s.update()
        output = stream.getvalue()
        assert output == ""

    def test_spinner_auto_animates(self):
        stream = _make_tty_stream()
        s = Spinner("Animating...", stream=stream)
        s._stop_event.wait = _controlled_wait(5)
        try:
            s.start()
            if s._thread is not None:
                s._thread.join()
        finally:
            s.stop()
        output = stream.getvalue()
        distinct_frames = {c for c in output if c in Spinner.FRAMES}
        assert len(distinct_frames) >= 2

    def test_animate_produces_distinct_frames(self):
        stream = _make_tty_stream()
        s = Spinner("Direct test", stream=stream)
        s._stop_event.wait = _controlled_wait(3)
        s._animate()
        output = stream.getvalue()
        frames_seen = [c for c in output if c in Spinner.FRAMES]
        assert len(frames_seen) >= 2

    def test_spinner_update_stores_suffix(self):
        stream = io.StringIO()
        s = Spinner("Suffix test", stream=stream)
        s.start()
        try:
            s.update(" (500 records)")
            assert s._suffix == " (500 records)"
        finally:
            s.stop()

    def test_spinner_suffix_appears_in_output(self):
        stream = _make_tty_stream()
        s = Spinner("Loading", stream=stream)
        s._stop_event.wait = _controlled_wait(3)
        s.update(" (42 items)")  # stored even before start
        s._suffix = " (42 items)"
        s._animate()
        output = stream.getvalue()
        assert "(42 items)" in output

    def test_spinner_non_tty_no_thread(self):
        stream = io.StringIO()
        s = Spinner("No thread", stream=stream)
        s.start()
        try:
            assert s._thread is None
        finally:
            s.stop()

    def test_spinner_stop_joins_thread(self):
        stream = _make_tty_stream()
        s = Spinner("Join test", stream=stream)
        s._stop_event.wait = _controlled_wait(2)
        s.start()
        s.stop()
        assert s._thread is None

    def test_spinner_exception_stops_thread(self):
        stream = _make_tty_stream()
        s = Spinner("Exception test", stream=stream)
        s._stop_event.wait = _controlled_wait(2)
        with pytest.raises(ValueError):
            with s:
                raise ValueError("boom")
        assert s._thread is None

    def test_spinner_double_start_ignored(self):
        stream = _make_tty_stream()
        s = Spinner("Double start", stream=stream)
        s._stop_event.wait = _controlled_wait(2)
        try:
            s.start()
            first_thread = s._thread
            s.start()  # should be a no-op
            assert s._thread is first_thread
        finally:
            s.stop()

    def test_spinner_update_after_stop(self):
        stream = io.StringIO()
        s = Spinner("After stop", stream=stream)
        s.start()
        s.stop()
        s.update(" should not crash")
        assert s._suffix == ""  # suffix unchanged — update was a no-op

    def test_spinner_reuse_after_stop(self):
        stream = _make_tty_stream()
        s = Spinner("Reuse test", stream=stream)
        s._stop_event.wait = _controlled_wait(2)
        s.start()
        s.stop()

        # Second cycle — use 0 ticks so the thread exits before rendering
        s._stop_event.wait = _controlled_wait(0)
        s.start()
        try:
            assert s._running
            assert s._thread is not None
            assert not s._line_written  # reset by start()
        finally:
            s.stop()

    def test_animate_handles_broken_stream_write(self):
        stream = _make_tty_stream()
        s = Spinner("Broken write", stream=stream)
        s._stop_event.wait = _controlled_wait(3)
        original_write = stream.write
        call_count = 0

        def failing_write(data):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise OSError("broken pipe")
            return original_write(data)

        stream.write = failing_write
        s._animate()  # should not raise

    def test_animate_handles_broken_stream_flush(self):
        stream = _make_tty_stream()
        s = Spinner("Broken flush", stream=stream)
        s._stop_event.wait = _controlled_wait(3)

        def failing_flush():
            raise OSError("broken pipe")

        stream.flush = failing_flush
        s._animate()  # should not raise


class TestPhaseTracker:
    def test_phase_tracker_increments(self):
        stream = io.StringIO()
        tracker = PhaseTracker(3, stream=stream)

        with tracker.phase("First"):
            pass
        with tracker.phase("Second"):
            pass
        with tracker.phase("Third"):
            pass

        output = stream.getvalue()
        assert "[1/3]" in output
        assert "[2/3]" in output
        assert "[3/3]" in output

    def test_phase_tracker_quiet_mode(self):
        stream = io.StringIO()
        tracker = PhaseTracker(2, stream=stream, quiet=True)

        with tracker.phase("First"):
            pass
        with tracker.phase("Second"):
            pass

        output = stream.getvalue()
        assert output == ""

    def test_phase_tracker_no_color(self):
        stream = io.StringIO()
        tracker = PhaseTracker(2, stream=stream, no_color=True)

        with tracker.phase("Test"):
            pass

        output = stream.getvalue()
        assert "\033[36m" not in output  # cyan
        assert "\033[32m" not in output  # green
        assert "\033[2m" not in output  # dim
        assert "\033[0m" not in output  # reset

    def test_phase_returns_null_spinner_when_quiet(self):
        tracker = PhaseTracker(1, quiet=True)
        spinner = tracker.phase("Test")
        assert isinstance(spinner, _NullSpinner)


class TestNullSpinner:
    def test_null_spinner_context_manager(self):
        with _NullSpinner() as s:
            s.update()
            s.update("suffix")

    def test_null_spinner_manual_methods(self):
        s = _NullSpinner()
        s.start()
        s.update()
        s.stop()
        s.stop(success=False)
