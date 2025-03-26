"""Shim for typing-related, annotation-related, and other symbols to avoid runtime dependencies on expensive or
third-party imports like `typing` or `typing-extensions`.

Warning: Do not directly import annotation-related symbols from this module (e.g. `from ._typing_compat import Any`)!
Doing so will trigger the module-level `__getattr__`, causing `typing` to get imported. Instead, import the module and
use symbols via attribute access as needed (e.g. `from . import _typing_compat [as _t]`). To avoid those symbols being
evaluated at runtime, which would also cause `typing` to get imported, make sure to put
`from __future__ import annotations` at the top of the module.
"""

from __future__ import annotations

import os  # noqa: F401 # Used in StrPath.
import sys


TYPE_CHECKING = False


__all__ = (
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
    "Optional",
    "TextIO",
    "Union",
    "TypeAlias",  # >=3.10
    # types
    "FrameType",
    "ModuleType",
    "SimpleNamespace",
    # Other
    "TYPE_CHECKING",
    "StrPath",
    "T",
    "U",
    "CallableT",
)


def __getattr__(name: str) -> object:
    if name in {"Callable", "Generator", "Iterable", "Iterator"}:
        global Callable, Generator, Iterable, Iterator

        from collections.abc import Callable, Generator, Iterable, Iterator

        return globals()[name]

    if name == "AbstractContextManager":
        global AbstractContextManager

        from contextlib import AbstractContextManager

        return AbstractContextManager

    if name in {"Any", "BinaryIO", "Optional", "TextIO", "Union"}:
        global Any, BinaryIO, Optional, TextIO, Union

        from typing import Any, BinaryIO, Optional, TextIO, Union

        return globals()[name]

    if sys.version_info >= (3, 10) and name == "TypeAlias":
        global TypeAlias

        from typing import TypeAlias

        return globals()[name]

    if name in {"FrameType", "ModuleType", "SimpleNamespace"}:
        global FrameType, ModuleType, SimpleNamespace

        from types import FrameType, ModuleType, SimpleNamespace

        return globals()[name]

    if name in {"T", "U", "CallableT"}:
        global T, U, CallableT

        from collections.abc import Callable
        from typing import TypeVar

        T = TypeVar("T")
        U = TypeVar("U")
        CallableT = TypeVar("CallableT", bound=Callable[..., object])

        return globals()[name]

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted(globals().keys() | set(__all__))


if TYPE_CHECKING:
    from typing_extensions import TypeAlias
elif sys.version_info < (3, 10):

    class TypeAlias:
        """Placeholder for typing.TypeAlias."""


StrPath: TypeAlias = "Union[str, os.PathLike[str]]"
