"""
Read resources contained within a package.

This codebase is shared between importlib.resources in the stdlib
and importlib_resources in PyPI. See
https://github.com/python/importlib_metadata/wiki/Development-Methodology
for more detail.
"""

from ._common import (
    Anchor,
    Package,
    as_file,
    files,
)
from ._functional import (
    contents,
    is_resource,
    open_binary,
    open_text,
    path,
    read_binary,
    read_text,
)

__all__ = [
    'Package',
    'Anchor',
    'ResourceReader',
    'as_file',
    'files',
    'contents',
    'is_resource',
    'open_binary',
    'open_text',
    'path',
    'read_binary',
    'read_text',
]


def __getattr__(name: str, /) -> object:
    if name == "ResourceReader":
        global ResourceReader

        from .abc import ResourceReader

        return ResourceReader

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted(globals().keys() | {"ResourceReader"})
