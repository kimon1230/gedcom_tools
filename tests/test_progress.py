"""Tests for progress indicator module."""

import io
import os
from unittest.mock import patch

import pytest

from gedcom_tools.progress import Colors, PhaseTracker, Spinner, _NullSpinner


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
        stream = io.StringIO()
        stream.isatty = lambda: True
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
        stream = io.StringIO()
        stream.isatty = lambda: True
        with Spinner("Testing...", stream=stream) as s:
            s.update()
        output = stream.getvalue()
        assert "⠋" in output or "⠙" in output
        assert "\r" in output

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
        stream = io.StringIO()
        stream.isatty = lambda: True
        with Spinner("Testing...", stream=stream, no_color=True):
            pass
        output = stream.getvalue()
        # Color codes should not be present (36m=cyan, 32m=green, 31m=red, etc.)
        # But cursor control codes like \033[K (clear line) are still allowed
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
        # Color codes should not be present
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
