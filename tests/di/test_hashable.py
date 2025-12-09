import pytest

from protest.di.hashable import UnhashableValueError, make_hashable


class TestMakeHashablePrimitives:
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="none"),
            pytest.param(True, id="bool_true"),
            pytest.param(False, id="bool_false"),
            pytest.param(42, id="int"),
            pytest.param(3.14, id="float"),
            pytest.param("hello", id="str"),
            pytest.param(b"bytes", id="bytes"),
        ],
    )
    def test_primitives_pass_through_unchanged(self, value: object) -> None:
        """Given a primitive value, when make_hashable is called, then it returns the same value."""
        result = make_hashable(value)
        assert result is value


class TestMakeHashableLists:
    def test_empty_list_becomes_empty_tuple(self) -> None:
        """Given an empty list, when make_hashable is called, then it returns an empty tuple."""
        result = make_hashable([])
        assert result == ()
        assert isinstance(result, tuple)

    def test_flat_list_becomes_tuple(self) -> None:
        """Given a flat list, when make_hashable is called, then it returns a tuple."""
        result = make_hashable([1, 2, 3])
        assert result == (1, 2, 3)

    def test_nested_list_becomes_nested_tuple(self) -> None:
        """Given a nested list, when make_hashable is called, then all levels become tuples."""
        result = make_hashable([[1, 2], [3, 4]])
        assert result == ((1, 2), (3, 4))

    def test_list_with_mixed_types(self) -> None:
        """Given a list with mixed types, when make_hashable is called, then all are converted."""
        result = make_hashable([1, "two", [3, 4], {"a": 5}])
        assert result == (1, "two", (3, 4), (("a", 5),))


class TestMakeHashableDicts:
    def test_empty_dict_becomes_empty_tuple(self) -> None:
        """Given an empty dict, when make_hashable is called, then it returns an empty tuple."""
        result = make_hashable({})
        assert result == ()

    def test_flat_dict_becomes_sorted_tuple_of_items(self) -> None:
        """Given a flat dict, when make_hashable is called, then keys are sorted."""
        result = make_hashable({"b": 2, "a": 1, "c": 3})
        assert result == (("a", 1), ("b", 2), ("c", 3))

    def test_nested_dict_is_recursively_converted(self) -> None:
        """Given a nested dict, when make_hashable is called, then all levels are converted."""
        result = make_hashable({"outer": {"inner": [1, 2]}})
        assert result == (("outer", (("inner", (1, 2)),)),)

    def test_dict_with_list_value(self) -> None:
        """Given a dict containing a list, when make_hashable is called, then list becomes tuple."""
        result = make_hashable({"ports": [5432, 5433]})
        assert result == (("ports", (5432, 5433)),)


class TestMakeHashableSets:
    def test_empty_set_becomes_empty_frozenset(self) -> None:
        """Given an empty set, when make_hashable is called, then it returns an empty frozenset."""
        result = make_hashable(set())
        assert result == frozenset()

    def test_flat_set_becomes_frozenset(self) -> None:
        """Given a flat set, when make_hashable is called, then it returns a frozenset."""
        result = make_hashable({1, 2, 3})
        assert result == frozenset({1, 2, 3})

    def test_frozenset_stays_frozenset(self) -> None:
        """Given a frozenset, when make_hashable is called, then it stays a frozenset."""
        original = frozenset({1, 2, 3})
        result = make_hashable(original)
        assert result == original


class TestMakeHashableTuples:
    def test_tuple_with_mutable_content_is_converted(self) -> None:
        """Given a tuple containing mutable values, when make_hashable is called, then contents are converted."""
        result = make_hashable(([1, 2], {"a": 3}))
        assert result == ((1, 2), (("a", 3),))


class TestMakeHashableCustomObjects:
    def test_hashable_custom_object_passes_through(self) -> None:
        """Given a hashable custom object, when make_hashable is called, then it passes through."""

        class HashableConfig:
            def __init__(self, name: str):
                self.name = name

            def __hash__(self) -> int:
                return hash(self.name)

            def __eq__(self, other: object) -> bool:
                return isinstance(other, HashableConfig) and self.name == other.name

        config = HashableConfig("test")
        result = make_hashable(config)
        assert result is config

    def test_unhashable_object_raises_error_with_path(self) -> None:
        """Given an unhashable object, when make_hashable is called, then UnhashableValueError is raised."""

        class UnhashableService:
            __hash__ = None  # type: ignore[assignment]

        service = UnhashableService()

        with pytest.raises(UnhashableValueError, match=r"type 'UnhashableService'"):
            make_hashable(service)

    def test_deeply_nested_unhashable_shows_path(self) -> None:
        """Given a deeply nested unhashable object, when make_hashable is called, then error shows path."""

        class Socket:
            __hash__ = None  # type: ignore[assignment]

        data = {"config": {"connections": [Socket()]}}

        with pytest.raises(
            UnhashableValueError, match=r"root\['config'\]\['connections'\]\[0\]"
        ):
            make_hashable(data)


class TestMakeHashableCacheKey:
    def test_same_content_produces_same_hash(self) -> None:
        """Given equivalent structures, when make_hashable is called, then results are equal."""
        dict_a = {"host": "localhost", "ports": [5432, 5433]}
        dict_b = {"ports": [5432, 5433], "host": "localhost"}

        key_a = make_hashable(dict_a)
        key_b = make_hashable(dict_b)

        assert key_a == key_b
        assert hash(key_a) == hash(key_b)

    def test_different_content_produces_different_hash(self) -> None:
        """Given different structures, when make_hashable is called, then results differ."""
        dict_a = {"ports": [5432]}
        dict_b = {"ports": [5433]}

        key_a = make_hashable(dict_a)
        key_b = make_hashable(dict_b)

        assert key_a != key_b
