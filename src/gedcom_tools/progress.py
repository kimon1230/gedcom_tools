"""Progress indicators for CLI feedback."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import IO, TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from types import TracebackType


class GlyphSet(NamedTuple):
    check: str
    cross: str
    arrow: str
    frames: str
    pair: str
    rule: str
    times: str
    dash: str


# rule is multiplied to draw table separators, so it has to stay one character
# wide in both sets. dash separates fields; it is not the table rule.
UNICODE_GLYPHS = GlyphSet("✓", "✗", "→", "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "↔", "─", "×", "—")
ASCII_GLYPHS = GlyphSet("[OK]", "[!]", "->", "|/-\\", "<->", "-", "x", "--")

# Encoding is handled by cli._harden_streams(); this is purely about whether the
# terminal has a font that can draw the things. Windows console fonts routinely
# lack braille and render the spinner as a row of boxes, and nothing about the
# stream reveals that - so it's a switch, not a detection.
_ascii_forced = False
_ASCII_OFF_VALUES = frozenset({"", "0", "false", "no"})


def set_ascii_mode(enabled: bool) -> None:
    """Force ASCII decorations for the rest of the process."""
    global _ascii_forced
    _ascii_forced = enabled


def ascii_mode() -> bool:
    if _ascii_forced:
        return True
    value = os.environ.get("GEDCOM_TOOLS_ASCII", "")
    return value.strip().lower() not in _ASCII_OFF_VALUES


def glyphs() -> GlyphSet:
    return ASCII_GLYPHS if ascii_mode() else UNICODE_GLYPHS


class Colors:
    """ANSI color codes with automatic detection."""

    def __init__(self, stream: IO[str] | None = None, force_disable: bool = False):
        self._enabled = self._should_use_color(stream, force_disable)

    def _should_use_color(self, stream: IO[str] | None, force_disable: bool) -> bool:
        if force_disable:
            return False
        if os.environ.get("NO_COLOR"):
            return False
        if stream is None:
            return False
        if not hasattr(stream, "isatty"):
            return False
        return stream.isatty()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def cyan(self) -> str:
        return "\033[36m" if self._enabled else ""

    @property
    def green(self) -> str:
        return "\033[32m" if self._enabled else ""

    @property
    def red(self) -> str:
        return "\033[31m" if self._enabled else ""

    @property
    def yellow(self) -> str:
        return "\033[33m" if self._enabled else ""

    @property
    def dim(self) -> str:
        return "\033[2m" if self._enabled else ""

    @property
    def reset(self) -> str:
        return "\033[0m" if self._enabled else ""


class Spinner:
    """Animated spinner for showing activity.

    Animation runs automatically in a background thread. Use update()
    to display progress information like record counts.

        with Spinner("Processing...", stream=sys.stderr) as s:
            for i, item in enumerate(items):
                process(item)
                s.update(f" ({i+1} items)")
    """

    def __init__(
        self,
        message: str,
        stream: IO[str] | None = None,
        no_color: bool = False,
        show_timing: bool = False,
    ):
        self.message = message
        self.stream = stream if stream is not None else sys.stderr
        self.colors = Colors(self.stream, force_disable=no_color)
        self.glyphs = glyphs()
        self.is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        self.show_timing = show_timing
        self._frame = 0
        self._running = False
        self._line_written = False
        self._start_time: float | None = None
        self._suffix = ""
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._running:
            self.stop(success=exc_type is None)

    def start(self) -> None:
        """Start the spinner."""
        if self._running:
            return
        self._running = True
        self._start_time = time.perf_counter()
        self._frame = 0
        self._suffix = ""
        self._line_written = False
        self._stop_event.clear()
        if self.is_tty:
            self._thread = threading.Thread(
                target=self._animate, daemon=True, name="spinner-animate"
            )
            self._thread.start()

    def _animate(self) -> None:
        while not self._stop_event.wait(0.08):
            with self._lock:
                self._frame = (self._frame + 1) % len(self.glyphs.frames)
                try:
                    self._render()
                except (OSError, UnicodeError):
                    # UnicodeError escaping here would kill the thread and dump
                    # a traceback through the middle of the user's output.
                    break

    def update(self, suffix: str = "") -> None:
        """Update suffix text displayed after the spinner message."""
        if not self._running:
            return
        with self._lock:
            self._suffix = suffix

    def stop(self, success: bool = True) -> None:
        """Stop spinner and show final state."""
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        elapsed = ""
        if self.show_timing and self._start_time is not None:
            duration = time.perf_counter() - self._start_time
            if duration >= 1.0:
                elapsed = f" {self.colors.dim}({duration:.2f}s){self.colors.reset}"
            else:
                elapsed = (
                    f" {self.colors.dim}({duration*1000:.0f}ms){self.colors.reset}"
                )
        if success:
            icon = f"{self.colors.green}{self.glyphs.check}"
        else:
            icon = f"{self.colors.red}{self.glyphs.cross}"
        try:
            if self.is_tty and self._line_written:
                self.stream.write("\r\033[K")
            self.stream.write(f"{icon} {self.message}{elapsed}{self.colors.reset}\n")
            self.stream.flush()
        except UnicodeError:
            # Progress output is never worth failing a command over. The CLI
            # hardens its streams; a library caller may not have.
            pass

    # caller must hold _lock
    def _render(self) -> None:
        if not self.is_tty:
            return
        frame = self.glyphs.frames[self._frame]
        line = (
            f"{self.colors.cyan}{frame}{self.colors.reset} {self.message}{self._suffix}"
        )
        self.stream.write(f"\r\033[K{line}")
        self.stream.flush()
        self._line_written = True


class PhaseTracker:
    """Track progress through multiple phases.

    Usage:
        tracker = PhaseTracker(4)
        with tracker.phase("Detecting encoding"):
            detect_encoding(file)
        with tracker.phase("Parsing structure"):
            parse(file)
    """

    def __init__(
        self,
        total_phases: int,
        stream: IO[str] | None = None,
        no_color: bool = False,
        quiet: bool = False,
        verbose: bool = False,
    ):
        self.total = total_phases
        self.current = 0
        self.stream = stream if stream is not None else sys.stderr
        self.colors = Colors(self.stream, force_disable=no_color)
        self.quiet = quiet
        self.verbose = verbose
        self.no_color = no_color

    def phase(self, name: str) -> Spinner | _NullSpinner:
        """Start a new phase, return spinner context manager."""
        self.current += 1
        if self.quiet:
            return _NullSpinner()
        prefix = f"{self.colors.dim}[{self.current}/{self.total}]{self.colors.reset}"
        return Spinner(
            f"{prefix} {name}",
            stream=self.stream,
            no_color=self.no_color,
            show_timing=self.verbose,
        )


class _NullSpinner:
    """No-op spinner for quiet mode."""

    def __enter__(self) -> _NullSpinner:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass

    def start(self) -> None:
        pass

    def update(self, suffix: str = "") -> None:
        pass

    def stop(self, success: bool = True) -> None:
        pass
