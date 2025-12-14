"""Tests for BDD-style step context managers."""

from __future__ import annotations

import asyncio

import pytest

from protest import ProTestSession
from protest.core.runner import TestRunner
from protest.events.types import Event
from protest.execution.capture import (
    reset_current_node_id,
    set_current_node_id,
)
from protest.steps import (
    StepInfo,
    add_step_callback,
    remove_step_callback,
    step,
    step_sync,
)


class TestStepBasic:
    """Basic step functionality tests."""

    @pytest.mark.asyncio
    async def test_step_emits_success_event(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::node")
        try:
            async with step("Do something"):
                pass
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        # Should have start + success
        assert len(events) == 2
        assert events[0].status == "start"
        assert events[0].name == "Do something"
        assert events[1].status == "success"
        assert events[1].duration is not None

    @pytest.mark.asyncio
    async def test_step_emits_failure_event(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::node")
        try:
            with pytest.raises(ValueError):
                async with step("Fail here"):
                    raise ValueError("boom")
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        # Should have start + failure
        assert len(events) == 2
        assert events[1].status == "failure"
        assert events[1].error is not None

    @pytest.mark.asyncio
    async def test_step_reraises_exception(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::node")
        try:
            with pytest.raises(RuntimeError, match="original error"):
                async with step("Will fail"):
                    raise RuntimeError("original error")
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

    @pytest.mark.asyncio
    async def test_step_includes_node_id(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("my::test::node")
        try:
            async with step("Test step"):
                pass
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        assert events[0].node_id == "my::test::node"


class TestStepSync:
    """Synchronous step tests."""

    def test_step_sync_emits_success_event(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::sync")
        try:
            with step_sync("Sync step"):
                pass
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        assert len(events) == 2
        assert events[1].status == "success"

    def test_step_sync_emits_failure_event(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::sync")
        try:
            with pytest.raises(RuntimeError), step_sync("Sync fail"):
                raise RuntimeError("error")
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        assert events[1].status == "failure"


class TestStepCapture:
    """Integration with ProTest capture system."""

    def test_step_events_in_full_test_run(self) -> None:
        session = ProTestSession(default_reporter=False)
        results: list = []
        session.events.on(Event.TEST_FAIL, lambda r: results.append(r))

        step_events: list[StepInfo] = []
        add_step_callback(step_events.append)

        @session.test()
        async def test_with_steps() -> None:
            async with step("Given setup"):
                pass
            async with step("When action"):
                raise AssertionError("expected failure")

        try:
            TestRunner(session).run()
        finally:
            remove_step_callback(step_events.append)

        assert len(results) == 1
        # Filter to only success/failure events (not start)
        completed_steps = [s for s in step_events if s.status != "start"]
        assert len(completed_steps) == 2
        assert completed_steps[0].status == "success"
        assert completed_steps[0].name == "Given setup"
        assert completed_steps[1].status == "failure"
        assert completed_steps[1].name == "When action"


class TestStepNested:
    """Nested steps behavior."""

    @pytest.mark.asyncio
    async def test_nested_steps_both_emit_events(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::nested")
        try:
            async with step("Outer"), step("Inner"):
                pass
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        # start outer, start inner, success inner, success outer
        assert len(events) == 4
        completed = [e for e in events if e.status != "start"]
        assert completed[0].name == "Inner"
        assert completed[1].name == "Outer"

    @pytest.mark.asyncio
    async def test_nested_step_failure_propagates(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        token = set_current_node_id("test::nested")
        try:
            with pytest.raises(ValueError):
                async with step("Outer"):
                    async with step("Inner"):
                        raise ValueError("inner error")
        finally:
            reset_current_node_id(token)
            remove_step_callback(events.append)

        completed = [e for e in events if e.status != "start"]
        assert completed[0].name == "Inner"
        assert completed[0].status == "failure"
        assert completed[1].name == "Outer"
        assert completed[1].status == "failure"


class TestStepConcurrent:
    """Concurrent step isolation."""

    @pytest.mark.asyncio
    async def test_concurrent_steps_have_correct_node_ids(self) -> None:
        events: list[StepInfo] = []
        add_step_callback(events.append)

        async def task(name: str) -> None:
            token = set_current_node_id(f"test::{name}")
            try:
                async with step(f"{name} step"):
                    await asyncio.sleep(0.01)
            finally:
                reset_current_node_id(token)

        try:
            await asyncio.gather(task("A"), task("B"))
        finally:
            remove_step_callback(events.append)

        # Each task should have its own node_id
        a_events = [e for e in events if e.node_id == "test::A"]
        b_events = [e for e in events if e.node_id == "test::B"]

        assert len(a_events) == 2  # start + success
        assert len(b_events) == 2
        assert a_events[1].name == "A step"
        assert b_events[1].name == "B step"
