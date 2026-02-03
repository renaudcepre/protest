"""Immutable hierarchical suite path value object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


@dataclass(frozen=True, slots=True)
class SuitePath:
    """Immutable hierarchical suite path like 'Parent::Child::GrandChild'.

    Encapsulates all path manipulation logic to avoid hardcoded '::' separators
    throughout the codebase.
    """

    SEPARATOR: ClassVar[str] = "::"
    _path: str

    @classmethod
    def from_parts(cls, parts: Sequence[str]) -> SuitePath:
        """Create from list of parts: ['Parent', 'Child'] -> 'Parent::Child'."""
        return cls(cls.SEPARATOR.join(parts))

    @property
    def parts(self) -> tuple[str, ...]:
        """Split into parts: 'A::B::C' -> ('A', 'B', 'C')."""
        return tuple(self._path.split(self.SEPARATOR)) if self._path else ()

    def ancestors(self) -> Iterator[SuitePath]:
        """Yield all ancestors from root to self (inclusive).

        Example: 'A::B::C' yields SuitePath('A'), SuitePath('A::B'), SuitePath('A::B::C')
        """
        parts = self.parts
        for i in range(1, len(parts) + 1):
            yield SuitePath.from_parts(parts[:i])

    def is_ancestor_of(self, other: SuitePath) -> bool:
        """Check if self is ancestor of other (or equal).

        Example: SuitePath('A::B').is_ancestor_of(SuitePath('A::B::C')) -> True
        """
        return other._path == self._path or other._path.startswith(
            self._path + self.SEPARATOR
        )

    def child(self, name: str) -> SuitePath:
        """Create a child path: 'A::B'.child('C') -> 'A::B::C'."""
        if not self._path:
            return SuitePath(name)
        return SuitePath(f"{self._path}{self.SEPARATOR}{name}")

    def lower(self) -> str:
        """Return lowercase string representation for case-insensitive comparison."""
        return self._path.lower()

    def __str__(self) -> str:
        return self._path

    def __bool__(self) -> bool:
        return bool(self._path)
