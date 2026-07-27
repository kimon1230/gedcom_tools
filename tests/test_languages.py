from __future__ import annotations

import json
import unicodedata
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock

import pytest

from gedcom_tools.cli import main
from gedcom_tools.commands.languages import (
    FAM_NON_EVENT_TAGS,
    INDI_NON_EVENT_TAGS,
    EventMatch,
    LanguageRow,
    LanguagesCollector,
    LanguagesResult,
    _resolve_language,
)
from gedcom_tools.constants import EXIT_SUCCESS, EXIT_USAGE_ERROR
from gedcom_tools.language_detect import (
    DEFAULT_LANGUAGES,
    LANGUAGE_NAMES,
    MIN_TEXT_LENGTH_DEFAULT,
    GedcomLanguageDetector,
)
from gedcom_tools.progress import Colors
from gedcom_tools.utils import EncodingInfo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def detector():
    """Shared detector — loads language models once for all unit tests."""
    return GedcomLanguageDetector()


class _StubDetector:
    """Lightweight stand-in for GedcomLanguageDetector.

    Classifies text by Unicode script instead of loading the full model.
    Used in integration tests to avoid the ~5s model preload.
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
    """Replace GedcomLanguageDetector with a fast stub everywhere."""
    monkeypatch.setattr(
        "gedcom_tools.commands.languages.GedcomLanguageDetector", _StubDetector
    )
    monkeypatch.setattr(
        "gedcom_tools.commands.stats.collector.GedcomLanguageDetector", _StubDetector
    )


def _ged(tmp_path: Path, name: str, body: str) -> Path:
    """Write a minimal GEDCOM file and return its path."""
    path = tmp_path / name
    path.write_text(
        "0 HEAD\n" "1 GEDC\n" "2 VERS 5.5.1\n" "1 CHAR UTF-8\n" f"{body}" "0 TRLR\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# GedcomLanguageDetector unit tests
# ---------------------------------------------------------------------------


class TestDetector:
    def test_builds_with_preloaded_models(self, detector):
        assert detector is not None
        assert detector._detector is not None

    def test_english(self, detector):
        code, skipped = detector.detect(
            "The weather in London has been particularly cold this winter"
        )
        assert code == "en"
        assert skipped is False

    def test_greek(self, detector):
        code, skipped = detector.detect(
            "Ο καιρός στην Αθήνα είναι ιδιαίτερα ζεστός το καλοκαίρι"
        )
        assert code == "el"
        assert skipped is False

    def test_german(self, detector):
        code, skipped = detector.detect(
            "Das Wetter in Berlin war diesen Winter besonders kalt"
        )
        assert code == "de"
        assert skipped is False

    def test_french(self, detector):
        code, skipped = detector.detect(
            "Le temps à Paris est très agréable au printemps"
        )
        assert code == "fr"
        assert skipped is False

    def test_latin(self, detector):
        code, skipped = detector.detect(
            "Gallia est omnis divisa in partes tres quarum unam incolunt Belgae"
            " aliam Aquitani tertiam qui ipsorum lingua Celtae nostra Galli appellantur"
        )
        assert code == "la"
        assert skipped is False

    def test_none_input(self, detector):
        code, skipped = detector.detect(None)
        assert code == "unknown"
        assert skipped is True

    def test_short_text_skipped(self, detector):
        code, skipped = detector.detect("Hello")
        assert code == "unknown"
        assert skipped is True

    def test_empty_string(self, detector):
        code, skipped = detector.detect("")
        assert code == "unknown"
        assert skipped is True

    def test_whitespace_only(self, detector):
        code, skipped = detector.detect("   \t\n  ")
        assert code == "unknown"
        assert skipped is True

    def test_nfc_normalization(self, detector):
        # NFD and NFC of the same French text should produce identical results
        nfc = "Le temps à Paris est très agréable au printemps"
        nfd = unicodedata.normalize("NFD", nfc)
        assert nfc != nfd  # they differ at byte level
        code_nfc, _ = detector.detect(nfc)
        code_nfd, _ = detector.detect(nfd)
        assert code_nfc == code_nfd

    def test_unrecognizable_input(self, detector):
        # Pure punctuation — pre-filter catches non-alphabetic input
        code, skipped = detector.detect("!@#$%^&*()!@#$%^&*()")
        assert code == "unknown"
        assert skipped is False

    def test_custom_min_length(self):
        det = GedcomLanguageDetector(min_length=50)
        assert det.min_length == 50
        code, skipped = det.detect("This text is under fifty characters.")
        assert code == "unknown"
        assert skipped is True

    def test_default_min_length(self):
        assert MIN_TEXT_LENGTH_DEFAULT == 10

    def test_alphabetic_prefilter_digits(self, detector):
        code, skipped = detector.detect("1234567890123456789")
        assert code == "unknown"
        assert skipped is False

    def test_alphabetic_prefilter_symbols(self, detector):
        code, skipped = detector.detect("+-=*/+-=*/+-=*/+-=*/")
        assert code == "unknown"
        assert skipped is False


class TestLanguageNames:
    def test_all_default_languages_have_names(self):
        """Every language in DEFAULT_LANGUAGES has a LANGUAGE_NAMES entry."""
        for code in DEFAULT_LANGUAGES:
            assert code in LANGUAGE_NAMES, f"Missing name for {code}"


class TestMarginAndConfidence:
    """Margin-based rejection and confidence floor."""

    def test_ambiguous_text_returns_unknown(self, detector):
        # "Debil mental" is ambiguous (Turkish vs Spanish) — margin too thin
        code, skipped = detector.detect("Debil mental")
        assert code == "unknown"
        assert skipped is False

    def test_confident_text_returns_language(self, detector):
        code, _ = detector.detect("This sentence is clearly written in English")
        assert code == "en"

    def test_low_confidence_mocked(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "en", "score": 0.2},
            {"lang": "fr", "score": 0.1},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "unknown"
        assert skipped is False

    def test_thin_margin_mocked(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "en", "score": 0.5},
            {"lang": "fr", "score": 0.45},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "unknown"
        assert skipped is False

    def test_wide_margin_mocked(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "en", "score": 0.8},
            {"lang": "fr", "score": 0.1},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "en"
        assert skipped is False


class TestCodeMap:
    def test_norwegian_mapped_to_nb(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "no", "score": 0.9},
            {"lang": "en", "score": 0.05},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "nb"
        assert skipped is False

    def test_unsupported_language_returns_unknown(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "sw", "score": 0.9},
            {"lang": "en", "score": 0.05},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "unknown"
        assert skipped is False


class TestModelSelection:
    def test_full_model_available_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "gedcom_tools.language_detect._full_model_cache_dir", lambda: tmp_path
        )
        from gedcom_tools.language_detect import _full_model_available

        assert _full_model_available() is False

    def test_full_model_available_true(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "gedcom_tools.language_detect._full_model_cache_dir", lambda: tmp_path
        )
        (tmp_path / "lid.176.bin").write_bytes(b"fake")
        from gedcom_tools.language_detect import _full_model_available

        assert _full_model_available() is True

    def test_auto_download_on_first_use(self, tmp_path, monkeypatch, capsys):
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            "gedcom_tools.language_detect._full_model_cache_dir", lambda: tmp_path
        )
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [{"lang": "en", "score": 0.99}]
        monkeypatch.setattr(
            "gedcom_tools.language_detect.LangDetector", lambda cfg: mock_detector
        )
        from gedcom_tools.language_detect import _ensure_full_model

        _ensure_full_model()
        err = capsys.readouterr().err
        assert "Downloading language model" in err
        assert "Download complete" in err

    def test_no_download_when_model_exists(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            "gedcom_tools.language_detect._full_model_cache_dir", lambda: tmp_path
        )
        (tmp_path / "lid.176.bin").write_bytes(b"fake")
        from gedcom_tools.language_detect import _ensure_full_model

        _ensure_full_model()
        err = capsys.readouterr().err
        assert err == ""


class TestResolveLanguage:
    def test_by_iso_code(self):
        assert _resolve_language("el") == ("Greek", "el")

    def test_by_full_name(self):
        assert _resolve_language("English") == ("English", "en")

    def test_case_insensitive_name(self):
        assert _resolve_language("GREEK") == ("Greek", "el")

    def test_case_insensitive_code(self):
        assert _resolve_language("EN") == ("English", "en")

    def test_multi_word_name(self):
        assert _resolve_language("norwegian bokmal") == ("Norwegian Bokmal", "nb")

    def test_unknown_returns_none(self):
        assert _resolve_language("Klingon") is None

    def test_partial_match_rejected(self):
        assert _resolve_language("Eng") is None

    def test_special_unknown_keyword(self):
        assert _resolve_language("unknown") == ("Unknown", "unknown")


# ---------------------------------------------------------------------------
# LanguageRow and LanguagesResult unit tests
# ---------------------------------------------------------------------------


class TestLanguageRow:
    def test_total_property(self):
        row = LanguageRow("English", "en", notes=5, stories=3, events=10)
        assert row.total == 18

    def test_total_all_zero(self):
        row = LanguageRow("Unknown", "unknown", notes=0, stories=0, events=0)
        assert row.total == 0


class TestLanguagesResult:
    def _make_result(self, **kwargs):
        defaults = {
            "file_path": "/tmp/test.ged",
            "encoding_info": EncodingInfo(
                encoding="UTF-8", has_bom=False, declared_charset="UTF-8"
            ),
            "rows": [],
            "total_texts": 0,
            "skipped_short": 0,
            "min_length": 10,
        }
        defaults.update(kwargs)
        return LanguagesResult(**defaults)

    def test_distinct_languages_excludes_unknown(self):
        result = self._make_result(
            rows=[
                LanguageRow("English", "en", 10, 5, 20),
                LanguageRow("Greek", "el", 5, 2, 8),
                LanguageRow("Unknown", "unknown", 3, 1, 2),
            ],
            total_texts=56,
        )
        assert result.distinct_languages == 2

    def test_distinct_languages_no_unknown(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 10, 5, 20)],
            total_texts=35,
        )
        assert result.distinct_languages == 1

    def test_format_text_table_layout(self):
        result = self._make_result(
            rows=[
                LanguageRow("English", "en", 10, 5, 20),
                LanguageRow("Greek", "el", 5, 2, 8),
            ],
            total_texts=50,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Language" in output
        assert "Notes" in output
        assert "Stories" in output
        assert "Events" in output
        assert "Total" in output
        assert "English" in output
        assert "Greek" in output
        assert "\u2500" in output  # separator line

    def test_format_text_totals_row(self):
        result = self._make_result(
            rows=[
                LanguageRow("English", "en", 10, 5, 20),
                LanguageRow("Greek", "el", 5, 2, 8),
            ],
            total_texts=50,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        total_lines = [
            line for line in output.split("\n") if line.strip().startswith("Total")
        ]
        assert len(total_lines) == 1

    def test_format_text_no_encoding(self):
        result = self._make_result(
            encoding_info=None,
            total_texts=5,
            rows=[LanguageRow("English", "en", 2, 1, 2)],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Encoding:" not in output
        assert "File:" in output

    def test_format_text_skip_count_shown(self):
        result = self._make_result(
            total_texts=10,
            skipped_short=5,
            rows=[LanguageRow("English", "en", 4, 3, 3)],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "(5 skipped, too short)" in output

    def test_format_text_skip_count_hidden_when_zero(self):
        result = self._make_result(
            total_texts=10,
            skipped_short=0,
            rows=[LanguageRow("English", "en", 4, 3, 3)],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "skipped" not in output

    def test_format_text_empty_no_notes(self):
        result = self._make_result(total_texts=0, skipped_short=0)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "No text content found" in output

    def test_format_text_empty_all_skipped(self):
        result = self._make_result(total_texts=0, skipped_short=12)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "All 12 text(s) were below the minimum length" in output

    def test_format_text_distinct_languages_line(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 5, 3, 7)],
            total_texts=15,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Distinct languages: 1" in output
        assert "excluding unknown" in output

    def test_format_text_category_legend(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 5, 3, 7)],
            total_texts=15,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Notes   = standalone top-level notes" in output
        assert "Stories = biographical notes on individuals" in output
        assert (
            "Events  = notes on births, deaths, marriages, and other events" in output
        )

    def test_format_text_legend_not_in_empty(self):
        result = self._make_result(total_texts=0, skipped_short=0)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Notes   =" not in output

    def test_format_text_language_hint(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 5, 3, 7)],
            total_texts=15,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "--language" in output

    def test_format_text_no_hint_when_empty(self):
        result = self._make_result(total_texts=0, skipped_short=0)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "--language" not in output

    def test_format_text_disclaimer_when_unknown(self):
        result = self._make_result(
            rows=[
                LanguageRow("English", "en", 5, 3, 7),
                LanguageRow("Unknown", "unknown", 2, 1, 0),
            ],
            total_texts=18,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "short or ambiguous" in output.lower()

    def test_format_text_no_disclaimer_without_unknown(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 5, 3, 7)],
            total_texts=15,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "short or ambiguous" not in output.lower()

    def test_format_json_structure(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 10, 5, 20)],
            total_texts=35,
            skipped_short=3,
        )
        data = json.loads(result.format_json())
        assert data["file"] == "/tmp/test.ged"
        assert data["mode"] == "aggregate"
        assert data["encoding"]["detected"] == "UTF-8"
        assert len(data["languages"]) == 1
        lang = data["languages"][0]
        assert lang["language"] == "English"
        assert lang["code"] == "en"
        assert lang["notes"] == 10
        assert lang["stories"] == 5
        assert lang["events"] == 20
        assert lang["total"] == 35
        assert data["summary"]["total_texts"] == 35
        assert data["summary"]["skipped_short"] == 3
        assert data["summary"]["distinct_languages"] == 1
        assert data["summary"]["min_length"] == 10
        cats = data["categories"]
        assert "notes" in cats
        assert "stories" in cats
        assert "events" in cats
        assert "disclaimer" in data
        assert "short or ambiguous" in data["disclaimer"].lower()

    def test_format_json_encoding_none(self):
        result = self._make_result(encoding_info=None)
        data = json.loads(result.format_json())
        assert data["encoding"] is None

    def test_quiet_mode(self):
        result = self._make_result(
            rows=[LanguageRow("English", "en", 5, 3, 7)],
            total_texts=15,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert "1 language(s) detected" in output
        assert "15 text(s)" in output

    def test_quiet_mode_empty(self):
        result = self._make_result(total_texts=0, skipped_short=0)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert output == ""


class TestLanguageFilterResult:
    def _make_result(self, **kwargs):
        defaults = {
            "file_path": "/tmp/test.ged",
            "encoding_info": EncodingInfo(
                encoding="UTF-8", has_bom=False, declared_charset="UTF-8"
            ),
            "rows": [],
            "total_texts": 5,
            "skipped_short": 0,
            "min_length": 10,
            "language_filter": "el",
            "language_filter_name": "Greek",
            "person_xrefs": [],
            "note_xrefs": [],
            "event_matches": [],
        }
        defaults.update(kwargs)
        return LanguagesResult(**defaults)

    def test_format_text_all_buckets(self):
        result = self._make_result(
            person_xrefs=[("@I1@", "Eleni"), ("@I2@", "Nikos")],
            note_xrefs=["@N1@"],
            event_matches=[EventMatch("@I1@", "BIRT", "Eleni")],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Persons with biographical notes (2):" in output
        assert "Eleni (@I1@)" in output
        assert "Standalone notes (1):" in output
        assert "@N1@" in output
        assert "Events with notes (1):" in output
        assert "@I1@  BIRT" in output

    def test_format_text_persons_only(self):
        result = self._make_result(
            person_xrefs=[("@I3@", "Maria")],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Persons with biographical notes (1):" in output
        assert "Maria (@I3@)" in output
        assert "Standalone notes" not in output
        assert "Events with notes" not in output

    def test_format_text_zero_matches(self):
        result = self._make_result(total_texts=8)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "No matches found for Greek (el)." in output

    def test_format_text_zero_total_texts(self):
        result = self._make_result(total_texts=0, skipped_short=0)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "No text content found" in output

    def test_format_text_all_skipped(self):
        result = self._make_result(total_texts=0, skipped_short=7)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "All 7 text(s) were below the minimum length" in output

    def test_format_text_analyzed_context_line(self):
        result = self._make_result(total_texts=12, skipped_short=3)
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Texts analyzed: 12" in output
        assert "(3 skipped, too short)" in output

    def test_format_text_encoding_info_none(self):
        result = self._make_result(encoding_info=None, person_xrefs=[("@I1@", "Eleni")])
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "File: /tmp/test.ged" in output
        assert "Encoding:" not in output

    def test_format_text_quiet_with_results(self):
        result = self._make_result(
            person_xrefs=[("@I1@", "Eleni"), ("@I2@", "Nikos"), ("@I3@", "Kostas")],
            note_xrefs=["@N1@"],
            event_matches=[
                EventMatch("@I1@", "BIRT", "Eleni"),
                EventMatch("@I2@", "DEAT", "Nikos"),
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert output == "Greek: 3 persons, 1 note, 2 events"

    def test_format_text_quiet_zero_matches(self):
        result = self._make_result(total_texts=3)
        colors = Colors(None, force_disable=True)
        assert result.format_text(colors, quiet=True) == ""

    def test_quiet_pluralization_singular(self):
        result = self._make_result(
            person_xrefs=[("@I1@", "Eleni")],
            note_xrefs=["@N1@"],
            event_matches=[EventMatch("@F1@", None, None)],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert "1 person," in output
        assert "1 note," in output
        assert "1 event" in output

    def test_quiet_pluralization_plural(self):
        result = self._make_result(
            person_xrefs=[("@I1@", "A"), ("@I2@", "B"), ("@I3@", "C")],
            note_xrefs=["@N1@", "@N2@", "@N3@"],
            event_matches=[
                EventMatch("@F1@", "MARR", None),
                EventMatch("@F2@", "MARR", None),
                EventMatch("@F3@", "MARR", None),
                EventMatch("@F4@", "MARR", None),
            ],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True)
        assert "3 persons" in output
        assert "3 notes" in output
        assert "4 events" in output

    def test_format_text_event_tag_none_renders_family_note(self):
        result = self._make_result(
            event_matches=[EventMatch("@F3@", None, None)],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "@F3@  (family note)" in output

    def test_format_text_xref_sort_order(self):
        result = self._make_result(
            note_xrefs=["@N1@", "@N2@", "@N3@"],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        n1 = output.index("@N1@")
        n2 = output.index("@N2@")
        n3 = output.index("@N3@")
        assert n1 < n2 < n3

    def test_format_text_person_name_next_to_xref(self):
        result = self._make_result(
            person_xrefs=[("@I5@", "Eleni Papadimitriou")],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        assert "Eleni Papadimitriou (@I5@)" in output

    def test_format_text_person_name_empty(self):
        result = self._make_result(
            person_xrefs=[("@I5@", "")],
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors)
        lines_with_xref = [line for line in output.splitlines() if "@I5@" in line]
        assert len(lines_with_xref) == 1
        assert lines_with_xref[0].strip() == "(@I5@)"

    def test_format_json_structure(self):
        result = self._make_result(
            person_xrefs=[("@I5@", "Eleni")],
            note_xrefs=["@N1@"],
            event_matches=[EventMatch("@I5@", "BIRT", "Eleni")],
        )
        data = json.loads(result.format_json())
        assert data["file"] == "/tmp/test.ged"
        assert data["mode"] == "filter"
        assert data["language"] == "Greek"
        assert data["code"] == "el"
        assert isinstance(data["persons"], list)
        assert isinstance(data["notes"], list)
        assert isinstance(data["events"], list)
        assert "summary" in data

    def test_format_json_total_matches(self):
        result = self._make_result(
            person_xrefs=[("@I1@", "A"), ("@I2@", "B")],
            note_xrefs=["@N1@", "@N2@", "@N3@"],
            event_matches=[EventMatch("@F1@", "MARR", None)],
        )
        data = json.loads(result.format_json())
        assert data["summary"]["total_matches"] == 6
        assert data["summary"]["person_count"] == 2
        assert data["summary"]["note_count"] == 3
        assert data["summary"]["event_count"] == 1

    def test_format_json_encoding_none(self):
        result = self._make_result(encoding_info=None)
        data = json.loads(result.format_json())
        assert data["encoding"] is None

    def test_format_json_event_tag_null(self):
        result = self._make_result(
            event_matches=[EventMatch("@F3@", None, None)],
        )
        data = json.loads(result.format_json())
        assert len(data["events"]) == 1
        assert data["events"][0]["event_tag"] is None

    def test_format_json_event_asdict_keys(self):
        result = self._make_result(
            event_matches=[EventMatch("@I5@", "BIRT", "Eleni")],
        )
        data = json.loads(result.format_json())
        event = data["events"][0]
        assert set(event.keys()) == {"parent_xref", "event_tag", "name"}
        assert event["parent_xref"] == "@I5@"
        assert event["event_tag"] == "BIRT"
        assert event["name"] == "Eleni"


# ---------------------------------------------------------------------------
# LanguagesCollector unit tests (mocked detector, no GEDCOM parsing)
# ---------------------------------------------------------------------------


class TestCollectorLogic:
    def test_detect_and_count_none(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c._detect_and_count(None, "stories")
        assert c.total_texts == 0
        assert c.skipped_short == 0
        c.detector.detect.assert_not_called()

    def test_detect_and_count_empty(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c._detect_and_count("", "stories")
        assert c.total_texts == 0
        c.detector.detect.assert_not_called()

    def test_detect_and_count_whitespace(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c._detect_and_count("   \t  ", "stories")
        assert c.total_texts == 0
        c.detector.detect.assert_not_called()

    def test_detect_and_count_skipped_short(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c.detector.detect.return_value = ("unknown", True)
        c._detect_and_count("short txt", "notes")
        assert c.skipped_short == 1
        assert c.total_texts == 0

    def test_detect_and_count_detected(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c.detector.detect.return_value = ("en", False)
        c._detect_and_count("Some longer text here for detection", "stories")
        assert c.total_texts == 1
        assert c.lang_counts["en"]["stories"] == 1

    def test_cache_deduplicates_calls(self):
        """Same xref → detector called once, counting happens each time."""
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c.detector.detect.return_value = ("en", False)

        c._detect_and_count("Long enough text for detection", "stories", xref="@N1@")
        c._detect_and_count("Long enough text for detection", "stories", xref="@N1@")
        c._detect_and_count("Long enough text for detection", "stories", xref="@N1@")

        assert c.detector.detect.call_count == 1
        assert c.lang_counts["en"]["stories"] == 3
        assert c.total_texts == 3

    def test_cache_different_xrefs(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.detector = Mock(spec=GedcomLanguageDetector)
        c.detector.detect.return_value = ("en", False)

        c._detect_and_count("Text for first note item", "notes", xref="@N1@")
        c._detect_and_count("Text for second note item", "notes", xref="@N2@")

        assert c.detector.detect.call_count == 2

    def test_build_result_language_name(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.lang_counts["en"]["stories"] = 5
        c.total_texts = 5
        result = c._build_result(None)
        assert result.rows[0].language == "English"
        assert result.rows[0].code == "en"

    def test_build_result_unknown_fallback(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.lang_counts["unknown"]["notes"] = 3
        c.total_texts = 3
        result = c._build_result(None)
        assert result.rows[0].language == "Unknown"

    def test_build_result_unrecognized_code(self):
        """Code not in LANGUAGE_NAMES gets title-cased."""
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.lang_counts["xy"]["events"] = 2
        c.total_texts = 2
        result = c._build_result(None)
        assert result.rows[0].language == "Xy"

    def test_build_result_sorted_by_total(self):
        c = LanguagesCollector(Path("/fake"), quiet=True)
        c.lang_counts["el"]["notes"] = 10
        c.lang_counts["en"]["stories"] = 3
        c.total_texts = 13
        result = c._build_result(None)
        assert result.rows[0].code == "el"
        assert result.rows[1].code == "en"


class TestLanguageFilterCollectorLogic:
    def _make_collector(self, language_filter="en"):
        c = LanguagesCollector(
            Path("/fake"), quiet=True, language_filter=language_filter
        )
        c.detector = Mock(spec=GedcomLanguageDetector)
        c.detector.detect.return_value = ("en", False)
        return c

    def test_stories_populates_person_xrefs(self):
        c = self._make_collector()
        c._detect_and_count(
            "Long enough text for detection purposes",
            "stories",
            parent_xref="@I1@",
        )
        assert "@I1@" in c._person_xrefs

    def test_events_populates_event_matches(self):
        c = self._make_collector()
        c._detect_and_count(
            "Long enough text for detection purposes",
            "events",
            parent_xref="@I1@",
            event_tag="BIRT",
        )
        assert ("@I1@", "BIRT") in c._event_matches

    def test_notes_populates_note_xrefs(self):
        c = self._make_collector()
        c._detect_and_count(
            "Long enough text for detection purposes",
            "notes",
            xref="@N1@",
        )
        assert "@N1@" in c._note_xrefs

    def test_filter_mismatch_leaves_sets_empty(self):
        c = self._make_collector()
        c.detector.detect.return_value = ("el", False)
        c._detect_and_count(
            "Long enough text for detection purposes",
            "stories",
            parent_xref="@I1@",
        )
        assert len(c._person_xrefs) == 0

    def test_no_filter_leaves_sets_empty(self):
        c = self._make_collector(language_filter=None)
        c._detect_and_count(
            "Long enough text for detection purposes",
            "stories",
            parent_xref="@I1@",
        )
        assert len(c._person_xrefs) == 0

    def test_build_result_populates_filter_fields(self):
        c = LanguagesCollector(Path("/fake"), quiet=True, language_filter="en")
        c.detector = Mock(spec=GedcomLanguageDetector)
        c._person_xrefs = {"@I1@", "@I2@"}
        c._note_xrefs = {"@N1@"}
        c._event_matches = {("@I1@", "BIRT"), ("@F1@", None)}
        c._indi_names = {"@I1@": "John Doe", "@I2@": "Jane Doe"}
        c.total_texts = 5
        c.skipped_short = 1

        result = c._build_result(None)

        assert result.language_filter == "en"
        assert result.language_filter_name == "English"
        assert len(result.person_xrefs) == 2
        assert len(result.note_xrefs) == 1
        assert len(result.event_matches) == 2
        assert result.rows == []


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------


class TestLanguagesCLI:
    def test_help_shows_min_length(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["languages", "--help"])
        assert exc.value.code == 0
        assert "--min-length" in capsys.readouterr().out

    def test_languages_in_top_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        assert "languages" in capsys.readouterr().out

    def test_missing_file(self):
        assert main(["languages", "nonexistent.ged"]) == EXIT_USAGE_ERROR

    @pytest.mark.usefixtures("_fast_lingua")
    def test_sample_file(self, sample_gedcom_path):
        assert main(["languages", str(sample_gedcom_path)]) == EXIT_SUCCESS

    @pytest.mark.usefixtures("_fast_lingua")
    def test_json_output_parseable(self, sample_gedcom_path, capsys):
        result = main(["--format", "json", "languages", str(sample_gedcom_path)])
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert "languages" in data
        assert "summary" in data
        assert data["mode"] == "aggregate"

    @pytest.mark.usefixtures("_fast_lingua")
    def test_quiet_mode(self, sample_gedcom_path, capsys):
        assert main(["-q", "languages", str(sample_gedcom_path)]) == EXIT_SUCCESS

    @pytest.mark.usefixtures("_fast_lingua")
    def test_no_color(self, sample_gedcom_path):
        assert (
            main(["--no-color", "languages", str(sample_gedcom_path)]) == EXIT_SUCCESS
        )

    @pytest.mark.usefixtures("_fast_lingua")
    def test_min_length_flag(self, sample_gedcom_path):
        assert (
            main(["languages", "--min-length", "20", str(sample_gedcom_path)])
            == EXIT_SUCCESS
        )

    @pytest.mark.usefixtures("_fast_lingua")
    def test_run_directly(self, tmp_path):
        from gedcom_tools.commands.languages import run

        f = _ged(tmp_path, "basic.ged", "0 @I1@ INDI\n1 NAME John /Doe/\n1 SEX M\n")
        args = Namespace(
            file=f,
            format="text",
            quiet=True,
            verbose=False,
            no_color=True,
            min_length=10,
        )
        assert run(args) == EXIT_SUCCESS

    @pytest.mark.usefixtures("_fast_lingua")
    def test_run_error_handling(self, tmp_path, capsys):
        from gedcom_tools.commands.languages import run

        f = tmp_path / "bad.ged"
        f.write_text("not a valid gedcom file\n", encoding="utf-8")
        args = Namespace(
            file=f,
            format="text",
            quiet=True,
            verbose=False,
            no_color=True,
            min_length=10,
        )
        result = run(args)
        assert result != EXIT_SUCCESS


class TestAutoDownload:
    def test_download_failure_propagates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "gedcom_tools.language_detect._full_model_cache_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            "gedcom_tools.language_detect.LangDetector",
            lambda cfg: (_ for _ in ()).throw(OSError("network error")),
        )
        from gedcom_tools.language_detect import _ensure_full_model

        with pytest.raises(OSError, match="network error"):
            _ensure_full_model()


class TestDetectorEdgeCases:
    def test_empty_result_from_detector(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = []
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "unknown"
        assert skipped is False

    def test_exception_from_detector(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.side_effect = RuntimeError("model error")
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "unknown"
        assert skipped is False

    def test_single_result_no_second(self):
        from unittest.mock import MagicMock

        det = GedcomLanguageDetector()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            {"lang": "en", "score": 0.9},
        ]
        det._detector = mock_detector
        code, skipped = det.detect("Some text that is long enough for detection")
        assert code == "en"
        assert skipped is False


@pytest.mark.usefixtures("_fast_lingua")
class TestLanguageFilterCLI:
    def test_language_english_exits_success(self, sample_gedcom_path):
        rc = main(["languages", "--language", "English", str(sample_gedcom_path)])
        assert rc == EXIT_SUCCESS

    def test_language_by_iso_code(self, sample_gedcom_path):
        rc = main(["languages", "--language", "en", str(sample_gedcom_path)])
        assert rc == EXIT_SUCCESS

    def test_language_json_mode_filter(self, sample_gedcom_path, capsys):
        rc = main(
            [
                "--format",
                "json",
                "languages",
                "--language",
                "English",
                str(sample_gedcom_path),
            ]
        )
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["mode"] == "filter"

    def test_unknown_language_exits_usage_error(self, sample_gedcom_path, capsys):
        rc = main(["languages", "--language", "Klingon", str(sample_gedcom_path)])
        assert rc == EXIT_USAGE_ERROR
        assert "Unknown language" in capsys.readouterr().err

    def test_error_message_shows_supported(self, sample_gedcom_path, capsys):
        main(["languages", "--language", "Klingon", str(sample_gedcom_path)])
        err = capsys.readouterr().err
        assert any(name in err for name in ("English", "Greek", "German"))
        assert "unknown" in err

    def test_language_quiet_single_line(self, sample_gedcom_path, capsys):
        rc = main(["-q", "languages", "--language", "Greek", str(sample_gedcom_path)])
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out.strip()
        assert "\n" not in out

    def test_language_verbose_phases(self, sample_gedcom_path, capsys):
        rc = main(["-v", "languages", "--language", "English", str(sample_gedcom_path)])
        assert rc == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Detecting encoding" in captured.err

    def test_run_with_language_in_namespace(self, tmp_path):
        from gedcom_tools.commands.languages import run

        f = _ged(tmp_path, "basic.ged", "0 @I1@ INDI\n1 NAME John /Doe/\n1 SEX M\n")
        args = Namespace(
            file=f,
            format="text",
            quiet=True,
            verbose=False,
            no_color=True,
            min_length=10,
            language="English",
        )
        assert run(args) == EXIT_SUCCESS

    def test_sample_file_regression(self, sample_gedcom_path):
        rc = main(["languages", "--language", "English", str(sample_gedcom_path)])
        assert rc == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# Integration tests — inline GEDCOM with stubbed detector
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_fast_lingua")
class TestLanguagesIntegration:
    def _collect(self, tmp_path, body, **kwargs):
        f = _ged(tmp_path, "test.ged", body)
        defaults = {"quiet": True, "no_color": True}
        defaults.update(kwargs)
        collector = LanguagesCollector(f, **defaults)
        return collector.collect()

    def test_indi_note_as_story(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.stories == 1
        assert en.events == 0
        assert en.notes == 0

    def test_event_sub_note_as_event(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 BIRT\n"
            "2 DATE 15 MAR 1850\n"
            "2 NOTE Born in the early morning at the family estate\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.events == 1
        assert en.stories == 0

    def test_unreferenced_note_as_notes(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This is a standalone note that nobody references\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.notes == 1
        assert en.stories == 0
        assert en.events == 0

    def test_pointer_classified_by_reference_site(self, tmp_path):
        """Pointer note under INDI → 'stories', not 'notes'."""
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This is a shared note about a person in the family\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE @N1@\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.stories == 1
        assert en.notes == 0

    def test_pointer_from_fam_as_event(self, tmp_path):
        """Pointer note under FAM → 'events'."""
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This is a note about a family event or ceremony\n"
            "0 @F1@ FAM\n"
            "1 NOTE @N1@\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.events == 1
        assert en.notes == 0

    def test_same_note_referenced_twice(self, tmp_path):
        """Same top-level NOTE from INDI and FAM — counted twice."""
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This shared note is referenced from both places\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE @N1@\n"
            "0 @F1@ FAM\n"
            "1 NOTE @N1@\n",
        )
        assert result.total_texts == 2
        en = next(r for r in result.rows if r.code == "en")
        assert en.stories == 1
        assert en.events == 1
        assert en.notes == 0

    def test_fam_level_note(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 NOTE A note directly under the family record for events\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.events == 1

    def test_fam_event_sub_note(self, tmp_path):
        """Note under FAM/MARR → events."""
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 MARR\n"
            "2 NOTE The marriage took place at the local church building\n",
        )
        assert result.total_texts == 1
        en = next(r for r in result.rows if r.code == "en")
        assert en.events == 1

    def test_sour_excluded_indi(self, tmp_path):
        """Note under INDI/SOUR is NOT classified as event."""
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 SOUR @S1@\n"
            "2 NOTE This citation note should be excluded from analysis\n",
        )
        assert result.total_texts == 0

    def test_sour_excluded_fam(self, tmp_path):
        """Note under FAM/SOUR is NOT classified as event."""
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 SOUR @S1@\n"
            "2 NOTE This family citation note should be excluded entirely\n",
        )
        assert result.total_texts == 0

    def test_no_notes_empty_result(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n1 NAME John /Doe/\n1 SEX M\n",
        )
        assert result.total_texts == 0
        assert result.skipped_short == 0
        assert len(result.rows) == 0

    def test_orphan_pointer_no_crash(self, tmp_path):
        """Pointer to non-existent NOTE → silently ignored."""
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n" "1 NAME John /Doe/\n" "1 NOTE @N99@\n",
        )
        assert result.total_texts == 0
        assert result.skipped_short == 0

    def test_min_length_boundary(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE 1234567890\n"  # exactly 10 chars → detected
            "1 BIRT\n"
            "2 NOTE 123456789\n",  # 9 chars → skipped
            min_length=10,
        )
        assert result.total_texts == 1
        assert result.skipped_short == 1

    def test_multiple_languages(self, tmp_path):
        """English and Greek text classified as different languages."""
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is an English biographical note about someone\n"
            "0 @I2@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
        )
        assert result.total_texts == 2
        assert result.distinct_languages == 2
        codes = {r.code for r in result.rows}
        assert "en" in codes
        assert "el" in codes

    def test_inline_and_pointer_mixed(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This top level note is referenced below by individual\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE @N1@\n"
            "1 NOTE This is an inline note directly on the individual record\n",
        )
        assert result.total_texts == 2
        en = next(r for r in result.rows if r.code == "en")
        assert en.stories == 2

    def test_empty_note_value(self, tmp_path):
        """NOTE tag with no text → silently ignored."""
        result = self._collect(tmp_path, "0 @I1@ INDI\n1 NAME John /Doe/\n1 NOTE\n")
        assert result.total_texts == 0
        assert result.skipped_short == 0

    def test_cont_continuation(self, tmp_path):
        """CONT lines handled transparently by ged4py."""
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE First line of a multi-line note\n"
            "2 CONT Second line continues the note text here\n",
        )
        assert result.total_texts == 1

    def test_verbose_shows_phases(self, tmp_path, capsys):
        f = _ged(tmp_path, "test.ged", "0 @I1@ INDI\n1 NAME John /Doe/\n")
        collector = LanguagesCollector(f, quiet=False, verbose=True, no_color=True)
        collector.collect()
        err = capsys.readouterr().err
        assert "Detecting encoding" in err
        assert "Loading language model" in err

    @pytest.mark.usefixtures("_fast_lingua")
    def test_royal92_ansel(self):
        """ANSEL-encoded file processes without crash."""
        royal92 = FIXTURES_DIR / "royal92.ged"
        if not royal92.exists():
            pytest.skip("royal92.ged not in fixtures")
        assert main(["languages", str(royal92)]) == EXIT_SUCCESS


@pytest.mark.usefixtures("_fast_lingua")
class TestLanguageFilterIntegration:
    def _collect(self, tmp_path, body, **kwargs):
        f = _ged(tmp_path, "test.ged", body)
        defaults = {"quiet": True, "no_color": True}
        defaults.update(kwargs)
        collector = LanguagesCollector(f, **defaults)
        return collector.collect()

    def test_indi_greek_story(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.person_xrefs) == 1
        xref, name = result.person_xrefs[0]
        assert xref == "@I1@"
        assert isinstance(name, str)

    def test_english_excluded(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is an English biographical note about a person\n",
            language_filter="el",
        )
        assert result.person_xrefs == []
        assert result.event_matches == []
        assert result.note_xrefs == []

    def test_indi_no_name(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.person_xrefs) == 1
        assert result.person_xrefs[0] == ("@I1@", "")

    def test_event_note_greek(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 BIRT\n"
            "2 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.event_matches) == 1
        em = result.event_matches[0]
        assert em.parent_xref == "@I1@"
        assert em.event_tag == "BIRT"

    def test_standalone_note_greek(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert "@N1@" in result.note_xrefs
        assert result.person_xrefs == []

    def test_person_dedup(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n"
            "1 NOTE Ένα δεύτερο ελληνικό σημείωμα για το ίδιο άτομο εδώ\n",
            language_filter="el",
        )
        xrefs = [x for x, _ in result.person_xrefs]
        assert xrefs.count("@I1@") == 1

    def test_event_dedup(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n"
            "0 @N2@ NOTE Ένα δεύτερο ελληνικό σημείωμα για το ίδιο γεγονός εδώ\n"
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 BIRT\n"
            "2 NOTE @N1@\n"
            "2 NOTE @N2@\n",
            language_filter="el",
        )
        birt_matches = [em for em in result.event_matches if em.event_tag == "BIRT"]
        assert len(birt_matches) == 1

    def test_mixed_languages(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is an English biographical note about a person here\n"
            "0 @I2@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        xrefs = [x for x, _ in result.person_xrefs]
        assert "@I2@" in xrefs
        assert "@I1@" not in xrefs

    def test_pointer_note_resolved(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n"
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE @N1@\n",
            language_filter="el",
        )
        assert len(result.person_xrefs) == 1
        assert result.person_xrefs[0][0] == "@I1@"

    def test_fam_direct_note(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.event_matches) == 1
        em = result.event_matches[0]
        assert em.parent_xref == "@F1@"
        assert em.event_tag is None
        assert em.name is None

    def test_fam_event_note(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 MARR\n"
            "2 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.event_matches) == 1
        em = result.event_matches[0]
        assert em.parent_xref == "@F1@"
        assert em.event_tag == "MARR"

    def test_pointer_story_and_event(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n"
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE @N1@\n"
            "1 BIRT\n"
            "2 NOTE @N1@\n",
            language_filter="el",
        )
        assert any(x == "@I1@" for x, _ in result.person_xrefs)
        assert any(
            em.parent_xref == "@I1@" and em.event_tag == "BIRT"
            for em in result.event_matches
        )

    def test_empty_results(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is an English biographical note about a person here\n",
            language_filter="el",
        )
        assert result.person_xrefs == []
        assert result.note_xrefs == []
        assert result.event_matches == []

    def test_min_length_filters(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n" "1 NAME Γιάννης /Παπαδόπουλος/\n" "1 NOTE Αυτό\n",
            language_filter="el",
            min_length=500,
        )
        assert result.person_xrefs == []
        assert result.event_matches == []

    def test_inline_note_parent_xref(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα κάποιου\n",
            language_filter="el",
        )
        assert len(result.person_xrefs) == 1
        assert result.person_xrefs[0][0] == "@I1@"

    def test_cont_continuation(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME Γιάννης /Παπαδόπουλος/\n"
            "1 BIRT\n"
            "2 NOTE Αυτό είναι ένα ελληνικό βιογραφικό σημείωμα\n"
            "3 CONT κάποιου με συνέχεια στη δεύτερη γραμμή\n",
            language_filter="el",
        )
        assert len(result.event_matches) == 1
        assert result.event_matches[0].event_tag == "BIRT"

    def test_language_unknown(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE !@#$%^&*()!@#$%^&*()\n",
            language_filter="unknown",
        )
        assert "@N1@" in result.note_xrefs

    def test_royal92_ansel_regression(self):
        royal92 = FIXTURES_DIR / "royal92.ged"
        if not royal92.exists():
            pytest.skip("royal92.ged not in fixtures")
        assert main(["languages", "--language", "en", str(royal92)]) == EXIT_SUCCESS


# ---------------------------------------------------------------------------
# --show-text tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_fast_lingua")
class TestShowText:
    def _collect(self, tmp_path, body, **kwargs):
        f = _ged(tmp_path, "test.ged", body)
        defaults = {"quiet": True, "no_color": True}
        defaults.update(kwargs)
        collector = LanguagesCollector(f, **defaults)
        return collector.collect()

    def test_show_text_without_language_exits_error(self, tmp_path):
        f = _ged(tmp_path, "t.ged", "0 @I1@ INDI\n1 NAME John /Doe/\n")
        rc = main(["languages", "--show-text", str(f)])
        assert rc == EXIT_USAGE_ERROR

    def test_show_text_error_before_file_validation(self, capsys):
        rc = main(["languages", "--show-text", "/nonexistent/path.ged"])
        assert rc == EXIT_USAGE_ERROR
        assert "--show-text requires --language" in capsys.readouterr().err

    def test_person_texts_in_text_output(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        assert "John Doe (@I1@)" in output
        assert "      This is a biographical note about John Doe person" in output

    def test_note_texts_in_text_output(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This standalone note has enough text for detection\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n",
            language_filter="en",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        assert "@N1@" in output
        assert "      This standalone note has enough text for detection" in output

    def test_event_texts_in_text_output(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 BIRT\n"
            "2 NOTE Born in the early morning at the family estate here\n",
            language_filter="en",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        assert "@I1@  BIRT" in output
        assert "      Born in the early morning at the family estate here" in output

    def test_json_persons_with_texts(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
            show_text=True,
        )
        data = json.loads(result.format_json(show_text=True))
        assert len(data["persons"]) == 1
        person = data["persons"][0]
        assert person["xref"] == "@I1@"
        assert "texts" in person
        assert "This is a biographical note about John Doe person" in person["texts"]

    def test_json_notes_object_form(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This standalone note has enough text for detection\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n",
            language_filter="en",
            show_text=True,
        )
        data = json.loads(result.format_json(show_text=True))
        assert len(data["notes"]) == 1
        note = data["notes"][0]
        assert note["xref"] == "@N1@"
        assert "texts" in note
        assert "This standalone note has enough text for detection" in note["texts"]

    def test_json_events_with_texts(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 BIRT\n"
            "2 NOTE Born in the early morning at the family estate here\n",
            language_filter="en",
            show_text=True,
        )
        data = json.loads(result.format_json(show_text=True))
        assert len(data["events"]) == 1
        event = data["events"][0]
        assert event["parent_xref"] == "@I1@"
        assert "texts" in event

    def test_no_texts_key_without_show_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
        )
        data = json.loads(result.format_json(show_text=False))
        if data["persons"]:
            assert "texts" not in data["persons"][0]
        if data["notes"]:
            assert "texts" not in data["notes"][0]

    def test_no_text_lines_without_show_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=False)
        six_space_lines = [ln for ln in output.splitlines() if ln.startswith("      ")]
        assert six_space_lines == []

    def test_notes_json_object_form_without_show_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This standalone note has enough text for detection\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n",
            language_filter="en",
        )
        data = json.loads(result.format_json(show_text=False))
        assert len(data["notes"]) == 1
        assert isinstance(data["notes"][0], dict)
        assert data["notes"][0]["xref"] == "@N1@"
        assert "texts" not in data["notes"][0]

    def test_multi_text_per_person(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE First biographical note about this person John Doe\n"
            "1 NOTE Second biographical note about this person John Doe\n",
            language_filter="en",
            show_text=True,
        )
        assert len(result.person_texts.get("@I1@", [])) == 2
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        assert "First biographical note" in output
        assert "Second biographical note" in output

    def test_pointer_note_shared_by_two_individuals(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This shared note is referenced from both persons here\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE @N1@\n"
            "0 @I2@ INDI\n"
            "1 NAME Jane /Doe/\n"
            "1 NOTE @N1@\n",
            language_filter="en",
            show_text=True,
        )
        assert len(result.person_xrefs) == 2
        assert "This shared note is referenced" in str(
            result.person_texts.get("@I1@", [])
        )
        assert "This shared note is referenced" in str(
            result.person_texts.get("@I2@", [])
        )

    def test_same_note_in_story_and_event(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @N1@ NOTE This note is used in both story and event contexts\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE @N1@\n"
            "1 BIRT\n"
            "2 NOTE @N1@\n",
            language_filter="en",
            show_text=True,
        )
        assert len(result.person_xrefs) == 1
        assert len(result.event_matches) == 1
        assert len(result.person_texts.get("@I1@", [])) >= 1
        assert len(result.event_texts.get("@I1@:BIRT", [])) >= 1

    def test_fam_event_note_with_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @F1@ FAM\n"
            "1 MARR\n"
            "2 NOTE The marriage took place at the local church building\n",
            language_filter="en",
            show_text=True,
        )
        assert len(result.event_matches) == 1
        key = "@F1@:MARR"
        assert "The marriage took place" in str(result.event_texts.get(key, []))

    def test_multiline_collapsed_in_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is the first line of a biographical note\n"
            "2 CONT and this is the second line continued here now\n",
            language_filter="en",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        text_lines = [ln for ln in output.splitlines() if ln.startswith("      ")]
        assert len(text_lines) == 1
        assert "first line" in text_lines[0]
        assert "second line" in text_lines[0]

    def test_multiline_preserved_in_json(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE First line of note\n"
            "2 CONT Second line of note\n",
            language_filter="en",
            show_text=True,
        )
        data = json.loads(result.format_json(show_text=True))
        person_texts = data["persons"][0]["texts"]
        assert any("\n" in t for t in person_texts)

    def test_quiet_text_suppresses_show_text(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, quiet=True, show_text=True)
        assert "\n" not in output
        assert "biographical" not in output

    def test_quiet_json_includes_texts(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="en",
            show_text=True,
        )
        data = json.loads(result.format_json(show_text=True))
        assert "texts" in data["persons"][0]

    def test_zero_matches_no_artifacts(self, tmp_path):
        result = self._collect(
            tmp_path,
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
            language_filter="el",
            show_text=True,
        )
        colors = Colors(None, force_disable=True)
        output = result.format_text(colors, show_text=True)
        assert "No matches found" in output
        six_space_lines = [ln for ln in output.splitlines() if ln.startswith("      ")]
        assert six_space_lines == []

    def test_cli_show_text_with_language(self, tmp_path, capsys):
        f = _ged(
            tmp_path,
            "t.ged",
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
        )
        rc = main(["languages", "--language", "English", "--show-text", str(f)])
        assert rc == EXIT_SUCCESS
        out = capsys.readouterr().out
        assert "biographical note" in out

    def test_cli_show_text_json(self, tmp_path, capsys):
        f = _ged(
            tmp_path,
            "t.ged",
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 NOTE This is a biographical note about John Doe person\n",
        )
        rc = main(
            ["--format", "json", "languages", "--language", "en", "--show-text", str(f)]
        )
        assert rc == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert "texts" in data["persons"][0]


# ---------------------------------------------------------------------------
# Non-event tag set tests
# ---------------------------------------------------------------------------


class TestNonEventTags:
    def test_indi_includes_sour(self):
        assert "SOUR" in INDI_NON_EVENT_TAGS

    def test_indi_includes_note(self):
        assert "NOTE" in INDI_NON_EVENT_TAGS

    def test_fam_includes_sour(self):
        assert "SOUR" in FAM_NON_EVENT_TAGS

    def test_fam_includes_note(self):
        assert "NOTE" in FAM_NON_EVENT_TAGS

    def test_fam_includes_husb_wife_chil(self):
        assert {"HUSB", "WIFE", "CHIL"}.issubset(FAM_NON_EVENT_TAGS)


# ---------------------------------------------------------------------------
# Stats integration — distinct_languages field
# ---------------------------------------------------------------------------


class TestStatsLanguageIntegration:
    @pytest.mark.usefixtures("_fast_lingua")
    def test_distinct_languages_populated(self, tmp_path):
        from gedcom_tools.commands.stats.collector import StatsCollector

        f = _ged(
            tmp_path,
            "lang.ged",
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 SEX M\n"
            "1 NOTE This is a long enough English note for detection\n",
        )
        result = StatsCollector(
            file_path=f, quiet=True, verbose=False, no_color=True
        ).collect()
        assert result.distinct_languages >= 1

    @pytest.mark.usefixtures("_fast_lingua")
    def test_distinct_languages_in_text_output(self, tmp_path):
        from gedcom_tools.commands.stats.collector import StatsCollector

        f = _ged(
            tmp_path,
            "lang.ged",
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 SEX M\n"
            "1 NOTE This is a long enough English note for detection\n",
        )
        result = StatsCollector(
            file_path=f, quiet=True, verbose=False, no_color=True
        ).collect()
        colors = Colors(None, force_disable=True)
        text = result.format_text(colors)
        assert "Distinct Languages:" in text

    @pytest.mark.usefixtures("_fast_lingua")
    def test_distinct_languages_in_json(self, tmp_path):
        from gedcom_tools.commands.stats.collector import StatsCollector

        f = _ged(
            tmp_path,
            "lang.ged",
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 SEX M\n"
            "1 NOTE This is a long enough English note for detection\n",
        )
        result = StatsCollector(
            file_path=f, quiet=True, verbose=False, no_color=True
        ).collect()
        data = json.loads(result.format_json())
        assert "distinct_languages" in data["records"]
        assert data["records"]["distinct_languages"] >= 1

    @pytest.mark.usefixtures("_fast_lingua")
    def test_no_notes_zero_languages(self, sample_gedcom_path):
        from gedcom_tools.commands.stats.collector import StatsCollector

        result = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        ).collect()
        assert result.distinct_languages == 0

    @pytest.mark.usefixtures("_fast_lingua")
    def test_quiet_includes_languages(self, tmp_path):
        from gedcom_tools.commands.stats.collector import StatsCollector

        f = _ged(tmp_path, "lang.ged", "0 @I1@ INDI\n1 NAME John /Doe/\n1 SEX M\n")
        result = StatsCollector(
            file_path=f, quiet=True, verbose=False, no_color=True
        ).collect()
        colors = Colors(None, force_disable=True)
        text = result.format_text(colors, quiet=True)
        assert "language(s)" in text

    @pytest.mark.usefixtures("_fast_lingua")
    def test_unreferenced_note_detected_in_stats(self, tmp_path):
        """Stats detects languages in unreferenced top-level notes."""
        from gedcom_tools.commands.stats.collector import StatsCollector

        f = _ged(
            tmp_path,
            "lang.ged",
            "0 @N1@ NOTE This is an unreferenced note with enough text\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Doe/\n"
            "1 SEX M\n",
        )
        result = StatsCollector(
            file_path=f, quiet=True, verbose=False, no_color=True
        ).collect()
        assert result.distinct_languages >= 1
