"""Tests for `EvalCase.tags` → `TestItem.tags` wiring.

Verifies that tags declared on an `EvalCase` via `tags=[...]` are merged
into the resulting `TestItem.tags` set, so that the `TagFilterPlugin`
(which filters on `TestItem.tags`) can honor them.

Eval functions are defined at module level to avoid `get_type_hints()`
resolution issues that occur with nested function definitions.
"""

from __future__ import annotations

from typing import Annotated

from protest import ForEach, From, ProTestSession
from protest.core.collector import Collector
from protest.evals import EvalCase
from protest.evals.suite import EvalSuite
from protest.tags.plugin import TagFilterPlugin

# Module-level case sources so `get_type_hints()` can resolve Annotated args.
_single_tagged = [EvalCase(inputs="x", name="c1", tags=["safety"])]
_multi_tagged = [EvalCase(inputs="x", name="c1", tags=["safety", "factual"])]
_mixed_cases = [
    EvalCase(inputs="x", name="c1", tags=["safety"]),
    EvalCase(inputs="y", name="c2", tags=["factual"]),
    EvalCase(inputs="z", name="c3"),
]
_no_tags_metadata = [
    EvalCase(inputs="x", name="c1", metadata={"other": "value"}),
]
_filter_cases = [
    EvalCase(inputs="a", name="c_safety", tags=["safety"]),
    EvalCase(inputs="b", name="c_factual", tags=["factual"]),
]


def _collect(cases: list[EvalCase]) -> list:
    """Build a session with a parametrized eval over `cases` and collect items."""
    session = ProTestSession()
    suite = EvalSuite("evals")

    source = ForEach(cases)

    @suite.eval()
    def my_eval(case: Annotated[EvalCase, From(source)]) -> str:
        return str(case.inputs)

    _ = my_eval  # silence unused-var diagnostics; decorator registers it
    session.add_suite(suite)
    return Collector().collect(session)


class TestCaseTagsMergedIntoItemTags:
    def test_single_case_tag_becomes_item_tag(self) -> None:
        items = _collect(_single_tagged)
        assert len(items) == 1
        assert "safety" in items[0].tags

    def test_multiple_case_tags(self) -> None:
        items = _collect(_multi_tagged)
        assert items[0].tags >= {"safety", "factual"}

    def test_cases_get_distinct_tags(self) -> None:
        items = _collect(_mixed_cases)
        assert len(items) == 3
        by_name = {item.case_ids[0]: item for item in items}
        assert "safety" in by_name["c1"].tags
        assert "factual" not in by_name["c1"].tags
        assert "factual" in by_name["c2"].tags
        assert "safety" not in by_name["c2"].tags
        assert by_name["c3"].tags == set()

    def test_case_with_metadata_only_has_no_tags(self) -> None:
        """`metadata` is user-free: no key (including 'tags') is interpreted."""
        items = _collect(_no_tags_metadata)
        assert items[0].tags == set()


class TestTagFilterHonorsCaseTags:
    """End-to-end: `TagFilterPlugin` filters items based on case tags."""

    def test_include_tag_keeps_matching_cases(self) -> None:
        items = _collect(_filter_cases)
        plugin = TagFilterPlugin(include_tags={"safety"})
        filtered = plugin.on_collection_finish(items)
        assert len(filtered) == 1
        assert filtered[0].case_ids == ["c_safety"]

    def test_exclude_tag_drops_matching_cases(self) -> None:
        items = _collect(_filter_cases)
        plugin = TagFilterPlugin(exclude_tags={"safety"})
        filtered = plugin.on_collection_finish(items)
        assert len(filtered) == 1
        assert filtered[0].case_ids == ["c_factual"]
