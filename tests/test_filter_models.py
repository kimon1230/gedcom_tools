from __future__ import annotations

import dataclasses

import pytest

from gedcom_tools.commands.filter.models import (
    FilterResult,
    FilterSpec,
    GedcomLine,
    GedcomRecord,
    RecordCounts,
)
from gedcom_tools.commands.filter.parser import _TAG_TO_FIELD


def _line() -> GedcomLine:
    return GedcomLine(
        level=0,
        xref="@I1@",
        tag="INDI",
        value=None,
        raw="0 @I1@ INDI",
        line_number=1,
    )


class TestSlots:
    """filter allocates one model per input line, so these must stay slotted."""

    def test_line_has_no_instance_dict(self) -> None:
        assert not hasattr(_line(), "__dict__")

    def test_record_has_no_instance_dict(self) -> None:
        record = GedcomRecord(header=_line(), children=[])
        assert not hasattr(record, "__dict__")

    def test_stray_attribute_is_rejected(self) -> None:
        with pytest.raises(AttributeError):
            _line().cached_surname = "Smith"  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "model",
        [GedcomLine, GedcomRecord, RecordCounts, FilterSpec, FilterResult],
    )
    def test_every_model_declares_slots(self, model: type) -> None:
        assert "__slots__" in model.__dict__

    def test_default_factory_still_per_instance(self) -> None:
        first, second = FilterSpec(), FilterSpec()
        first.strip_tags.append("_CUSTOM")
        assert second.strip_tags == []


class TestRecordCountsFields:
    def test_tag_map_only_names_declared_fields(self) -> None:
        # count_records() bumps these via setattr(); under slots an unmatched
        # name raises instead of quietly creating an attribute.
        declared = {f.name for f in dataclasses.fields(RecordCounts)}
        assert set(_TAG_TO_FIELD.values()) <= declared

    def test_setattr_path_works_under_slots(self) -> None:
        counts = RecordCounts()
        for field_name in _TAG_TO_FIELD.values():
            setattr(counts, field_name, getattr(counts, field_name) + 1)
        assert counts.total == len(_TAG_TO_FIELD)
