"""Compatibility imports for typing features across Python versions."""

import sys

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if sys.version_info >= (3, 13):
    from typing import TypeIs
else:
    from typing_extensions import TypeIs

__all__ = ["Self", "TypeIs"]
