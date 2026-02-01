"""Progress indicators for CLI feedback."""

from __future__ import annotations

import os
import sys
import time
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType


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

    Use as a context manager:
        with Spinner("Processing...") as s:
            for item in items:
                process(item)
                s.update()
    """

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

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
        self.is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()
        self.show_timing = show_timing
        self._frame = 0
        self._running = False
        self._line_written = False
        self._start_time: float | None = None

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
        self._running = True
        self._start_time = time.perf_counter()
        self._render()

    def update(self, suffix: str = "") -> None:
        """Advance spinner frame and optionally update suffix text."""
        if not self._running:
            return
        self._frame = (self._frame + 1) % len(self.FRAMES)
        self._render(suffix)

    def stop(self, success: bool = True) -> None:
        """Stop spinner and show final state."""
        self._running = False
        elapsed = ""
        if self.show_timing and self._start_time is not None:
            duration = time.perf_counter() - self._start_time
            if duration >= 1.0:
                elapsed = f" {self.colors.dim}({duration:.2f}s){self.colors.reset}"
            else:
                elapsed = (
                    f" {self.colors.dim}({duration*1000:.0f}ms){self.colors.reset}"
                )
        if self.is_tty and self._line_written:
            self.stream.write("\r\033[K")
        icon = f"{self.colors.green}✓" if success else f"{self.colors.red}✗"
        self.stream.write(f"{icon} {self.message}{elapsed}{self.colors.reset}\n")
        self.stream.flush()

    def _render(self, suffix: str = "") -> None:
        if not self.is_tty:
            return
        frame = self.FRAMES[self._frame]
        line = f"{self.colors.cyan}{frame}{self.colors.reset} {self.message}{suffix}"
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
