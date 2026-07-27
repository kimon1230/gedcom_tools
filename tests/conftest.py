from pathlib import Path

import pytest

from gedcom_tools import progress

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_ascii_mode(monkeypatch):
    """main() sets ASCII mode process-wide, so a --ascii test would otherwise
    leak into every test that runs after it."""
    monkeypatch.setattr(progress, "_ascii_forced", False)


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
