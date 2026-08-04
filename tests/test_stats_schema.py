from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from gedcom_tools.commands.stats.collector import StatsCollector

SCHEMA_PATH = Path(__file__).parent.parent / "docs" / "stats-schema.json"

# StatsCollector builds a real GedcomLanguageDetector for any file with INDI or
# FAM records, which fetches a 126 MB model on a cold cache. Nothing here asserts
# anything about detected languages, so the conftest stub stands in.
pytestmark = pytest.mark.usefixtures("_fast_lingua")


@pytest.fixture
def schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema)


class TestSchemaValidity:
    def test_schema_is_valid_json_schema(self, schema: dict) -> None:
        Draft202012Validator.check_schema(schema)

    def test_schema_has_required_top_level_fields(self, schema: dict) -> None:
        required = schema.get("required", [])
        assert "file" in required
        assert "records" in required
        assert "demographics" in required


class TestSchemaCompliance:
    def test_empty_file_conforms(
        self, tmp_path: Path, validator: Draft202012Validator
    ) -> None:
        ged = tmp_path / "empty.ged"
        ged.write_text(
            "0 HEAD\n" "1 GEDC\n" "2 VERS 5.5.1\n" "1 CHAR UTF-8\n" "0 TRLR\n",
            encoding="utf-8",
        )
        collector = StatsCollector(
            file_path=ged, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())
        validator.validate(data)

    def test_sample_file_conforms(
        self, sample_gedcom_path: Path, validator: Draft202012Validator
    ) -> None:
        collector = StatsCollector(
            file_path=sample_gedcom_path, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())
        validator.validate(data)

    def test_rich_data_conforms(
        self, tmp_path: Path, validator: Draft202012Validator
    ) -> None:
        ged = tmp_path / "rich.ged"
        ged.write_text(
            "0 HEAD\n"
            "1 GEDC\n"
            "2 VERS 5.5.1\n"
            "1 CHAR UTF-8\n"
            "0 @I1@ INDI\n"
            "1 NAME John /Smith/\n"
            "1 SEX M\n"
            "1 BIRT\n"
            "2 DATE 15 MAR 1850\n"
            "2 PLAC London, England\n"
            "1 DEAT\n"
            "2 DATE 20 JUN 1920\n"
            "1 FAMS @F1@\n"
            "0 @I2@ INDI\n"
            "1 NAME Mary /Jones/\n"
            "1 SEX F\n"
            "1 BIRT\n"
            "2 DATE 10 JAN 1855\n"
            "1 DEAT\n"
            "2 DATE 5 DEC 1930\n"
            "1 FAMS @F1@\n"
            "0 @I3@ INDI\n"
            "1 NAME James /Smith/\n"
            "1 SEX M\n"
            "1 BIRT\n"
            "2 DATE 1 FEB 1880\n"
            "1 FAMC @F1@\n"
            "0 @F1@ FAM\n"
            "1 HUSB @I1@\n"
            "1 WIFE @I2@\n"
            "1 CHIL @I3@\n"
            "1 MARR\n"
            "2 DATE 5 JUN 1875\n"
            "0 TRLR\n",
            encoding="utf-8",
        )
        collector = StatsCollector(
            file_path=ged, quiet=True, verbose=False, no_color=True
        )
        result = collector.collect()
        data = json.loads(result.format_json())
        validator.validate(data)

    def test_extra_field_rejected(self, validator: Draft202012Validator) -> None:
        data = {
            "file": "/test.ged",
            "encoding": None,
            "records": {
                "individuals": 0,
                "families": 0,
                "sources": 0,
                "locations": 0,
                "distinct_languages": 0,
            },
            "timeline": {
                "earliest_year": None,
                "latest_year": None,
                "earliest_generation": None,
                "date_span_years": None,
                "by_century": {},
                "lifespan": None,
            },
            "tree_structure": {
                "generation_depth": 0,
                "largest_families": [],
                "marriage": None,
            },
            "demographics": {
                "gender": {"male": 0, "female": 0, "unknown": 0},
                "surnames": [],
                "lineages": [],
                "given_names_male": [],
                "given_names_female": [],
            },
            "locations": [],
            "completeness": {},
            "life_events": {},
            "family_size": None,
            "birth_patterns": None,
            "lifespan_trends": None,
            "research_quality": {},
            "EXTRA_FIELD": "should fail",
        }
        with pytest.raises(ValidationError):
            validator.validate(data)
