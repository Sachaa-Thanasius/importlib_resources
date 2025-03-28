"""Shim for typing- and annotation-related symbols to avoid runtime dependencies on expensive or third-party imports
like `typing` or `typing-extensions`.

Warning: Do not directly import annotation-related symbols from this module (e.g. `from ._typing_compat import Any`)!
Doing so will trigger the module-level `__getattr__`, causing `typing` to get imported. Instead, import the module and
use symbols via attribute access as needed (e.g. `from . import _typing_compat [as _t]`). To avoid those symbols being
evaluated at runtime, which would also cause `typing` to get imported, make sure to put
`from __future__ import annotations` at the top of the module.
"""

from __future__ import annotations

import os  # Used in StrPath.
import sys


TYPE_CHECKING = False


__all__ = (
    # Used at runtime.
    "TYPE_CHECKING",
    "overload",
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
    "CallableT",
    "T",
)


def __getattr__(name: str) -> object:  # noqa: PLR0911
    if name in {"Callable", "Generator", "Iterable", "Iterator"}:
        global Callable, Generator, Iterable, Iterator

        from collections.abc import Callable, Generator, Iterable, Iterator

        return globals()[name]

    if name == "AbstractContextManager":
        global AbstractContextManager

        from contextlib import AbstractContextManager

        return globals()[name]

    if name in {"Any", "BinaryIO", "Literal", "Optional", "TextIO", "Union"}:
        global Any, BinaryIO, Literal, Optional, TextIO, Union

        from typing import Any, BinaryIO, Literal, Optional, TextIO, Union

        return globals()[name]

    if sys.version_info >= (3, 10) and name == "TypeAlias":
        global TypeAlias

        from typing import TypeAlias

        return globals()[name]

    if name in {"FrameType", "ModuleType", "SimpleNamespace"}:
        global FrameType, ModuleType, SimpleNamespace

        from types import FrameType, ModuleType, SimpleNamespace

        return globals()[name]

    if name == "StrPath":
        global StrPath

        import os
        from typing import Union

        if not TYPE_CHECKING:
            StrPath = Union[str, os.PathLike[str]]

        return globals()[name]

    if name == "T":
        global T

        from typing import TypeVar

        T = TypeVar("T")

        return globals()[name]

    if name == "CallableT":
        global CallableT

        from collections.abc import Callable
        from typing import TypeVar

        CallableT = TypeVar("CallableT", bound=Callable[..., object])

        return globals()[name]

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted(globals().keys() | __all__)


if TYPE_CHECKING:
    from typing_extensions import TypeAlias
elif sys.version_info < (3, 10):

    class TypeAlias:
        """Placeholder for typing.TypeAlias."""


# An annotated global can't be assigned within a function,
# and pyright won't recognize StrPath as a type alias without the TypeAlias annotation.
if TYPE_CHECKING:
    StrPath: TypeAlias = "Union[str, os.PathLike[str]]"


if TYPE_CHECKING:
    from typing import overload
else:

    def overload(f):  # noqa: ANN001, ANN202
        return f
