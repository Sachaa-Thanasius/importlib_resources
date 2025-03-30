"""
Read resources contained within a package.

This codebase is shared between importlib.resources in the stdlib
and importlib_resources in PyPI. See
https://github.com/python/importlib_metadata/wiki/Development-Methodology
for more detail.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import importlib.machinery
import os
import sys
import warnings

from . import _lazy as _l
from . import _lazy as _t
from . import abc
from .abc import ResourceReader


_ResourceReaderGetter: _t.TypeAlias = (
    "_t.Callable[[str], _t.Optional[abc.TraversableResources]]"
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


_MISSING: _t.Any = object()


# Backwards compat: Old alias.
Package: _t.TypeAlias = "_t.Union[_t.ModuleType, str]"

Anchor: _t.TypeAlias = Package
"""An anchor for resources, either a module object or a module name as a string."""


# ============================================================================
# region -------- Frame helpers --------
# ============================================================================


# This attempts to support Python implementations that either don't have sys._getframe()
# or don't support sys._getframe(x) where x >= 2, e.g. Jython, IronPython.
# This avoids inspect.stack() because of how expensive inspect is to import.
def _get_frame(depth: int = 1, /) -> _t.Optional[_t.FrameType]:
    """Return the frame object for one of the caller's parent stack frames."""

    try:
        return sys._getframe(depth + 1)
    except (AttributeError, ValueError):
        # For platforms without sys._getframe() or without a sufficiently capable one.

        global _get_frame

        def _get_frame(depth: int = 1, /) -> _t.Optional[_t.FrameType]:
            """Return the frame object for one of the caller's parent stack frames."""

            try:
                raise TypeError  # noqa: TRY301
            except TypeError:
                try:
                    frame = sys.exc_info()[2].tb_frame  # pyright: ignore [reportOptionalMemberAccess] # Guarded.
                    for _ in range(depth + 1):
                        frame = frame.f_back  # pyright: ignore [reportOptionalMemberAccess] # Guarded.
                    return frame  # noqa: TRY300
                except Exception:  # noqa: BLE001
                    global _get_frame

                    def _get_frame(depth: int = 1, /) -> _t.Optional[_t.FrameType]:
                        """Return the frame object for one of the caller's parent stack frames."""

                    return _get_frame()

        return _get_frame()


def _get_caller_module_name(depth: int = 1, default: str = "__main__") -> str:
    """Find the module name of the frame one level beyond the depth given."""

    try:
        return sys._getframemodulename(depth + 1) or default  # pyright: ignore # noqa: PGH003 # Guarded.
    except AttributeError:
        # For platforms without sys._getframemodulename().

        global _get_caller_module_name

        def _get_caller_module_name(depth: int = 1, default: str = "__main__") -> str:
            """Find the module name of the frame one level beyond the depth given."""

            try:
                return _get_frame(depth + 1).f_globals.get("__name__", default)  # pyright: ignore # noqa: PGH003 # Guarded.
            except (AttributeError, ValueError):
                # For platforms without a capable sys._getframe() or a traceback-accessible call stack.

                global _get_caller_module_name

                def _get_caller_module_name(
                    depth: int = 1,
                    default: str = "__main__",
                ) -> str:
                    """Find the module name of the frame one level beyond the depth given."""

                    msg = "Cannot get the caller's module's name."
                    raise RuntimeError(msg)

                return _get_caller_module_name(depth, default)

        return _get_caller_module_name(depth, default)


# endregion


# ============================================================================
# region -------- Forwards/backwards compatibility helpers --------
# ============================================================================


def _block_standard(reader_getter: _ResourceReaderGetter) -> _ResourceReaderGetter:
    """
    Wrap TraversableResourcesLoader._compat_get_resource_reader()
    and intercept any standard library readers.
    """

    @functools.wraps(reader_getter)
    def wrapper(
        *args: _t.Any,
        **kwargs: _t.Any,
    ) -> _t.Optional[abc.TraversableResources]:
        """
        If the reader is from the standard library, return None to allow
        allow likely newer implementations in this library to take precedence.
        """
        try:
            reader = reader_getter(*args, **kwargs)
        except NotADirectoryError:
            # MultiplexedPath may fail on zip subdirectory
            return None
        except ValueError as exc:
            # NamespaceReader in stdlib may fail for editable installs
            # (python/importlib_resources#311, python/importlib_resources#318)
            # Remove after bugfix applied to Python 3.13.
            if "not enough values to unpack" not in str(exc):
                raise
            return None

        # Python 3.10+
        mod_name = reader.__class__.__module__
        if mod_name.startswith('importlib.') and mod_name.endswith('readers'):
            return None

        # Python 3.8, 3.9
        if isinstance(
            reader, _CompatibilityFiles
        ) and reader.spec.loader.__class__.__module__.startswith((
            'zipimport',
            '_frozen_importlib_external',
        )):
            return None

        return reader

    return wrapper


def _skip_degenerate(reader: _t.T) -> _t.Optional[_t.T]:
    """
    Mask any degenerate reader. Ref python/importlib_resources#298.
    """
    is_degenerate = isinstance(reader, _CompatibilityFiles) and not reader._reader
    return reader if not is_degenerate else None


class _CompatibilityFiles(abc.TraversableResources):
    """
    Adapter for an existing or non-existent resource reader
    to provide a compatibility .files().
    """

    def __init__(self, spec: importlib.machinery.ModuleSpec):
        self.spec = spec

    @property
    def _reader(self) -> _t.Optional[abc.TraversableResources]:
        try:
            return self.spec.loader.get_resource_reader(self.spec.name)  # pyright: ignore  # noqa: PGH003 # Guarded.
        except AttributeError:
            pass

    def _native(self) -> abc.TraversableResources:
        """
        Return the native reader if it supports files().
        """
        reader = self._reader
        return reader if (reader is not None and hasattr(reader, 'files')) else self

    def __getattr__(self, attr: str, /) -> _t.Any:
        return getattr(self._reader, attr)

    def files(self) -> abc.Traversable:
        # Defer import for startup performance.
        from ._path_adapters import SpecPath

        return SpecPath(self.spec, self._reader)


class _TraversableResourcesLoader:
    """
    Adapt a loader to provide TraversableResources and other
    compatibility.

    Ensures the readers from importlib_resources are preferred
    over stdlib readers.
    """

    def __init__(self, spec: importlib.machinery.ModuleSpec):
        self.spec = spec

    def _zip_reader(self) -> _t.Optional[_l.readers.ZipReader]:
        try:
            return _l.readers.ZipReader(self.spec.loader, self.spec.name)  # pyright: ignore [reportArgumentType] # Guarded?
        except AttributeError:
            pass

    def _namespace_reader(self) -> _t.Optional[_l.readers.NamespaceReader]:
        try:
            return _l.readers.NamespaceReader(self.spec.submodule_search_locations)  # pyright: ignore [reportArgumentType] # Guarded?
        except (AttributeError, ValueError):
            pass

    def _file_reader(self) -> _t.Optional[_l.readers.FileReader]:
        try:
            path = _l.pathlib.Path(self.spec.origin)  # pyright: ignore [reportArgumentType] # Guarded.
        except TypeError:
            return None

        if path.exists():
            return _l.readers.FileReader(_t.SimpleNamespace(path=path))  # pyright: ignore [reportArgumentType] # .path is provided.
        else:
            return None

    def _standard_reader(self) -> _t.Optional[abc.TraversableResources]:
        return self._zip_reader() or self._namespace_reader() or self._file_reader()

    def _compat_get_resource_reader(self, name: str) -> abc.TraversableResources:
        return _CompatibilityFiles(self.spec)._native()

    def get_resource_reader(self, name: str) -> abc.TraversableResources:
        return (
            _skip_degenerate(_block_standard(self._compat_get_resource_reader)(name))
            or self._standard_reader()
            or self._compat_get_resource_reader(name)
        )


def _wrap_spec(spec: importlib.machinery.ModuleSpec) -> abc.TraversableResources:
    """
    Get the traversable resources reader for a module spec while wrapping missing functionality on the
    spec/loader/reader for compatibility.
    """

    loader = _TraversableResourcesLoader(spec)
    return loader.get_resource_reader(spec.name)


# endregion


# ============================================================================
# region -------- Base API --------
# ============================================================================


def _resolve(cand: _t.Optional[Anchor]) -> _t.ModuleType:
    if cand is None:
        # PYUPDATE: 3.15 - Update depth based on package_to_anchor() being removed.
        # Depth is 3 because
        # <caller>() (3) -> package_to_anchor() (2) -> files() (1) -> resolve() (0)
        cand = _get_caller_module_name(depth=3)

    if isinstance(cand, str):
        return importlib.import_module(cand)
    else:
        # This allows non-modules through, but we rely on from_package() to catch such cases.
        return cand


def _from_package(package: _t.ModuleType) -> abc.Traversable:
    """Get the Traversable object for the given package."""

    spec = package.__spec__
    assert spec is not None
    reader = _wrap_spec(spec)
    return reader.files()


def _package_to_anchor(
    func: _t.Callable[[_t.Optional[Anchor]], abc.Traversable],
) -> _t.Callable[[_t.Optional[Anchor]], abc.Traversable]:
    """
    Replace 'package' parameter as 'anchor' and warn about the change.

    Other errors should fall through.

    >>> files('a', 'b')
    Traceback (most recent call last):
    TypeError: files() takes from 0 to 1 positional arguments but 2 were given

    Remove this compatibility in Python 3.14.
    """

    @functools.wraps(func)
    def wrapper(
        anchor: _t.Optional[Anchor] = _MISSING,
        package: _t.Optional[Anchor] = _MISSING,
    ) -> abc.Traversable:
        # Base case: anchor usage.
        if (package is _MISSING) and (anchor is not _MISSING):
            return func(anchor)

        # Warning case: package usage.
        if (package is not _MISSING) and (anchor is _MISSING):
            warnings.warn(
                "First parameter to files is renamed to 'anchor'",
                DeprecationWarning,
                stacklevel=2,
            )
            return func(package)

        # Error cases: Both or neither provided. Expected to raise TypeError.
        if (package is not _MISSING) and (anchor is not _MISSING):
            return func(anchor, package)  # pyright: ignore [reportCallIssue, reportUnknownVariableType]
        else:
            return func()  # pyright: ignore [reportCallIssue, reportUnknownVariableType]

    return wrapper


@_package_to_anchor
def files(anchor: _t.Optional[Anchor] = None) -> abc.Traversable:
    """
    Get a Traversable resource for an anchor.
    """
    return _from_package(_resolve(anchor))


def _dir_exists(path: abc.Traversable) -> bool:
    """
    Some Traversables implement ``is_dir()`` to raise an
    exception (i.e. ``FileNotFoundError``) when the
    directory doesn't exist. This function wraps that call
    to always return a boolean and only return True
    if there's a dir and it exists.
    """
    try:
        return path.is_dir()
    except FileNotFoundError:
        pass
    return False


@contextlib.contextmanager
def _as_file_Path(path: _l.pathlib.Path) -> _t.Generator[_l.pathlib.Path]:
    """
    Degenerate behavior for pathlib.Path objects.
    """
    yield path


def _write_contents(
    target: _l.pathlib.Path,
    source: abc.Traversable,
) -> _l.pathlib.Path:
    child = target.joinpath(source.name)
    if source.is_dir():
        child.mkdir()
        for item in source.iterdir():
            _write_contents(child, item)
    else:
        child.write_bytes(source.read_bytes())
    return child


@contextlib.contextmanager
def _temp_dir(path: abc.Traversable) -> _t.Generator[_l.pathlib.Path]:
    """
    Given a traversable dir, recursively replicate the whole tree
    to the file system in a context manager.
    """
    assert path.is_dir()
    with _l.tempfile.TemporaryDirectory() as temp_dir:
        yield _write_contents(_l.pathlib.Path(temp_dir), path)


@contextlib.contextmanager
def _temp_file(
    reader: abc.Traversable,
    suffix: str = '',
    # gh-93353: Keep a reference to call os.remove() in late Python
    # finalization.
    *,
    _os_remove: _t.Callable[[str], None] = os.remove,
) -> _t.Generator[_l.pathlib.Path]:
    # Not using tempfile.NamedTemporaryFile as it leads to deeper 'try'
    # blocks due to the need to close the temporary file to work on Windows
    # properly.
    fd, raw_path = _l.tempfile.mkstemp(suffix=suffix)
    try:
        # Avoid loading the whole file in memory before transferring it.
        with reader.open("rb") as fsrc, open(fd, "wb") as fdest:  # noqa: PTH123 # Plain open is fine.
            _l.shutil.copyfileobj(fsrc, fdest)

        yield _l.pathlib.Path(raw_path)
    finally:
        try:
            _os_remove(raw_path)
        except FileNotFoundError:
            pass


def as_file(path: abc.Traversable) -> _t.AbstractContextManager[_l.pathlib.Path]:
    """
    Given a Traversable object, return that object as a
    path on the local file system in a context manager.
    """
    if isinstance(path, _l.pathlib.Path):
        return _as_file_Path(path)
    elif _dir_exists(path):
        return _temp_dir(path)
    else:
        return _temp_file(path, suffix=path.name)


# endregion


# ============================================================================
# region -------- Functional API --------
# ============================================================================


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


def _get_resource(
    anchor: _t.Optional[Anchor],
    path_names: tuple[_t.StrPath, ...],
) -> abc.Traversable:
    if anchor is None:
        msg = "anchor must be module or string, got None"
        raise TypeError(msg)
    return files(anchor).joinpath(*path_names)


def open_binary(anchor: Anchor, *path_names: _t.StrPath) -> _t.BinaryIO:
    """Open for binary reading the *resource* within *package*."""
    return _get_resource(anchor, path_names).open('rb')


def open_text(
    anchor: Anchor,
    *path_names: _t.StrPath,
    encoding: str = _MISSING,
    errors: str = 'strict',
) -> _t.TextIO:
    """Open for text reading the *resource* within *package*."""
    encoding = _get_encoding_arg(path_names, encoding)
    resource = _get_resource(anchor, path_names)
    return resource.open('r', encoding=encoding, errors=errors)


def read_binary(anchor: Anchor, *path_names: _t.StrPath) -> bytes:
    """Read and return contents of *resource* within *package* as bytes."""
    return _get_resource(anchor, path_names).read_bytes()


def read_text(
    anchor: Anchor,
    *path_names: _t.StrPath,
    encoding: str = _MISSING,
    errors: str = 'strict',
) -> str:
    """Read and return contents of *resource* within *package* as str."""
    encoding = _get_encoding_arg(path_names, encoding)
    resource = _get_resource(anchor, path_names)
    return resource.read_text(encoding=encoding, errors=errors)


def path(
    anchor: Anchor,
    *path_names: _t.StrPath,
) -> _t.AbstractContextManager[_l.pathlib.Path]:
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


# endregion
