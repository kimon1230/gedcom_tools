from __future__ import annotations

from gedcom_tools import constants
from gedcom_tools.commands import languages
from gedcom_tools.commands.stats import collector


class TestSharedTagSets:
    def test_non_event_tags_are_one_shared_object(self):
        """languages and stats must not drift apart on what counts as an event."""
        assert languages.INDI_NON_EVENT_TAGS is constants.INDI_NON_EVENT_TAGS
        assert collector.INDI_NON_EVENT_TAGS is constants.INDI_NON_EVENT_TAGS
        assert languages.FAM_NON_EVENT_TAGS is constants.FAM_NON_EVENT_TAGS
        assert collector.FAM_NON_EVENT_TAGS is constants.FAM_NON_EVENT_TAGS
