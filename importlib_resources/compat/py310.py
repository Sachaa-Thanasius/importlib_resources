from __future__ import annotations

import sys

import lazy_find

with lazy_find.lazy_finder:
    import typing as _t

TYPE_CHECKING = False


__all__ = ("TypeAlias",)


if sys.version_info >= (3, 11):
    TypeAlias: _t.TypeAlias = "_t.TypeAlias"
elif TYPE_CHECKING:
    from typing_extensions import TypeAlias
else:

    class TypeAlias:
        """Placeholder for typing.TypeAlias."""
