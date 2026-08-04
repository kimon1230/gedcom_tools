import unicodedata
from pathlib import Path

import pytest

from gedcom_tools import progress
from gedcom_tools.language_detect import MIN_TEXT_LENGTH_DEFAULT

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _StubDetector:
    """Lightweight stand-in for GedcomLanguageDetector.

    Classifies text by Unicode script instead of loading the full model.
    Keeps tests off the 126 MB CDN download and off the ~5s model preload.
    """

    def __init__(
        self, min_length: int = MIN_TEXT_LENGTH_DEFAULT, **kwargs: object
    ) -> None:
        self.min_length = min_length

    def detect(self, text: str | None) -> tuple[str, bool]:
        if text is None:
            return ("unknown", True)
        text = unicodedata.normalize("NFC", text).strip()
        if len(text) < self.min_length:
            return ("unknown", True)
        if not any(ch.isalpha() for ch in text):
            return ("unknown", False)
        for ch in text:
            if "\u0370" <= ch <= "\u03ff" or "\u1f00" <= ch <= "\u1fff":
                return ("el", False)
        return ("en", False)


@pytest.fixture
def _fast_lingua(monkeypatch):
    """Replace GedcomLanguageDetector with a fast stub everywhere.

    Both call sites import the class by name, so both have to be patched;
    anything that misses one downloads the real model.
    """
    monkeypatch.setattr(
        "gedcom_tools.commands.languages.GedcomLanguageDetector", _StubDetector
    )
    monkeypatch.setattr(
        "gedcom_tools.commands.stats.collector.GedcomLanguageDetector", _StubDetector
    )


@pytest.fixture(autouse=True)
def _reset_ascii_mode(monkeypatch):
    """main() sets ASCII mode process-wide, so a --ascii test would otherwise
    leak into every test that runs after it. ascii_mode() also reads the
    environment, so a runner that exports the variable would flip every
    default-mode assertion in the suite."""
    monkeypatch.setattr(progress, "_ascii_forced", False)
    monkeypatch.delenv("GEDCOM_TOOLS_ASCII", raising=False)


@pytest.fixture
def sample_gedcom_path():
    return FIXTURES_DIR / "555sample.ged"


@pytest.fixture
def minimal_gedcom_content():
    return """\
0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Doe/
1 SEX M
0 TRLR
"""


@pytest.fixture
def temp_gedcom_file(tmp_path, minimal_gedcom_content):
    gedcom_file = tmp_path / "test.ged"
    gedcom_file.write_text(minimal_gedcom_content, encoding="utf-8")
    return gedcom_file
