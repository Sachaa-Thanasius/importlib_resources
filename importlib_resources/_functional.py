"""Simplified function-based API for importlib.resources"""

from __future__ import annotations

import warnings

from . import _lazy_modules as _l
from . import _typing_compat as _t
from . import abc
from ._common import Anchor, as_file, files


_MISSING: _t.Any = object()


def _get_encoding_arg(path_names: tuple[_t.StrPath, ...], encoding: str) -> str:
    # For compatibility with versions where *encoding* was a positional
    # argument, it needs to be given explicitly when there are multiple
    # *path_names*.
    # This limitation can be removed in Python 3.15.
    if encoding is _MISSING:
        if len(path_names) > 1:
            msg = "'encoding' argument required with multiple path names"
            raise TypeError(msg)

        return 'utf-8'
    return encoding


def _get_resource(anchor: _t.Optional[Anchor], path_names: tuple[_t.StrPath, ...]) -> abc.Traversable:
    if anchor is None:
        msg = "anchor must be module or string, got None"
        raise TypeError(msg)
    return files(anchor).joinpath(*path_names)


def open_binary(anchor: Anchor, *path_names: _t.StrPath) -> _t.BinaryIO:
    """Open for binary reading the *resource* within *package*."""
    return _get_resource(anchor, path_names).open('rb')


def open_text(anchor: Anchor, *path_names: _t.StrPath, encoding: str = _MISSING, errors: str = 'strict') -> _t.TextIO:
    """Open for text reading the *resource* within *package*."""
    encoding = _get_encoding_arg(path_names, encoding)
    resource = _get_resource(anchor, path_names)
    return resource.open('r', encoding=encoding, errors=errors)


def read_binary(anchor: Anchor, *path_names: _t.StrPath) -> bytes:
    """Read and return contents of *resource* within *package* as bytes."""
    return _get_resource(anchor, path_names).read_bytes()


def read_text(anchor: Anchor, *path_names: _t.StrPath, encoding: str = _MISSING, errors: str = 'strict') -> str:
    """Read and return contents of *resource* within *package* as str."""
    encoding = _get_encoding_arg(path_names, encoding)
    resource = _get_resource(anchor, path_names)
    return resource.read_text(encoding=encoding, errors=errors)


def path(anchor: Anchor, *path_names: _t.StrPath) -> _t.AbstractContextManager[_l.pathlib.Path]:
    """Return the path to the *resource* as an actual file system path."""
    return as_file(_get_resource(anchor, path_names))


def is_resource(anchor: Anchor, *path_names: _t.StrPath) -> bool:
    """Return ``True`` if there is a resource named *name* in the package,

    Otherwise returns ``False``.
    """
    try:
        return _get_resource(anchor, path_names).is_file()
    except abc.TraversalError:
        return False


def contents(anchor: Anchor, *path_names: _t.StrPath) -> _t.Iterator[str]:
    """Return an iterable over the named resources within the package.

    The iterable returns :class:`str` resources (e.g. files).
    The iterable does not recurse into subdirectories.
    """
    warnings.warn(
        "importlib.resources.contents is deprecated. Use files(anchor).iterdir() instead.",
        DeprecationWarning,
        stacklevel=1,
    )
    return (resource.name for resource in _get_resource(anchor, path_names).iterdir())
