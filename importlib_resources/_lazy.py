"""INTERNAL.

A reexport shim/middleman for typing-related symbols, annotation-related symbols, and modules to avoid import-time
dependencies on expensive modules (like `typing` and `pathlib`) or third-party imports (like `typing-extensions`).
Some of the symbols or modules may eventually be needed at runtime, but their import/creation will be "on demand"
to improve startup performance.

Usage Notes
-----------
Do not directly import annotation-related symbols from this module (e.g. ``from ._lazy import Any``)!
Doing so will trigger the module-level `__getattr__`, causing shimmed modules, e.g. `typing`, to get imported.
Instead, import the module and use symbols via attribute access as needed (e.g. ``from . import _lazy [as _t]``).

Additionally, to avoid those symbols being evaluated at runtime, which would _also_ cause shimmed modules to get imported,
make sure to defer evaluation of annotations via the following:

    a) <3.14: Manual stringification of annotations, or `from __future__ import annotations`.
    b) >=3.14: Nothing, thanks to default PEP 649 semantics.
"""

from __future__ import annotations

import sys


TYPE_CHECKING = False


__all__ = (
    # ---- Modules ----

    # stdlib
    "pathlib",
    "shutil",
    "tempfile",

    # sibling
    "readers",

    # ---- Typing/annotation symbols ----

    # collections.abc
    "Callable",
    "Generator",
    "Iterable",
    "Iterator",

    # contextlib
    "AbstractContextManager",

    # typing
    "Any",
    "BinaryIO",
    "Literal",
    "NoReturn",
    "Optional",
    "TextIO",
    "Union",
    "TypeAlias",  # >=3.10

    # types
    "FrameType",
    "ModuleType",
    "SimpleNamespace",

    # Other
    "StrPath",
    "T",

    # ---- Used at runtime ----

    "TYPE_CHECKING",
    "overload",

)  # fmt: skip


# Type checkers needs this block to understand what __getattr__() does currently.
if TYPE_CHECKING:
    import os
    import pathlib
    import shutil
    import tempfile
    from collections.abc import Callable, Generator, Iterable, Iterator
    from contextlib import AbstractContextManager
    from types import FrameType, ModuleType, SimpleNamespace
    from typing import Any, BinaryIO, Literal, NoReturn, Optional, TextIO, TypeVar, Union

    from typing_extensions import TypeAlias

    from . import readers

    StrPath: TypeAlias = Union[str, os.PathLike[str]]

    T = TypeVar("T")


def __getattr__(name: str) -> object:
    if name == "pathlib":
        import pathlib as obj

    elif name == "shutil":
        import shutil as obj

    elif name == "tempfile":
        import tempfile as obj

    elif name == "readers":
        from . import readers as obj

    elif name in {"Callable", "Generator", "Iterable", "Iterator"}:
        import collections.abc

        obj = getattr(collections.abc, name)

    elif name == "AbstractContextManager":
        import contextlib

        obj = getattr(contextlib, name)

    elif name in {"Any", "BinaryIO", "Literal", "NoReturn", "Optional", "TextIO", "Union"} or (
        sys.version_info >= (3, 10) and name == "TypeAlias"
    ):
        import typing

        obj = getattr(typing, name)

    elif name in {"FrameType", "ModuleType", "SimpleNamespace"}:
        import types

        obj = getattr(types, name)

    elif name == "StrPath":
        import os
        from typing import Union

        obj = Union[str, os.PathLike[str]]

    elif name == "T":
        from typing import TypeVar

        # This will respond to queries for "T" and be cached in the global namespace as "T", so it's fine.
        obj = TypeVar("T")  # pyright: ignore[reportGeneralTypeIssues] # noqa: PLC0132

    else:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    # Cache the result in the global namespace to avoid re-calling __getattr__() (when possible).
    globals()[name] = obj
    return obj


def __dir__() -> list[str]:
    return sorted(globals().keys() | __all__)


if TYPE_CHECKING:
    from typing_extensions import TypeAlias
elif sys.version_info < (3, 10):

    class TypeAlias:
        """Placeholder for typing.TypeAlias."""


if TYPE_CHECKING:
    from typing import overload
else:

    def overload(f: object) -> object:
        return f
