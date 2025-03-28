from __future__ import annotations

import importlib
import os
import sys
import warnings

from . import _lazy_modules as _l
from . import _typing_compat as _t
from . import abc
from ._adapters import wrap_spec


Package: _t.TypeAlias = "_t.Union[_t.ModuleType, str]"
Anchor = Package

_undefined: _t.Any = object()


def _wraps(wrapped: _t.CallableT) -> _t.Callable[[_t.CallableT], _t.CallableT]:
    """A vendored version of `functools.wraps()` to avoid the heavy import."""

    def decorator(wrapper: _t.CallableT) -> _t.CallableT:
        for attr in ('__module__', '__name__', '__qualname__', '__doc__', '__annotations__', '__type_params__'):
            try:
                value = getattr(wrapped, attr)
            except AttributeError:  # noqa: PERF203
                pass
            else:
                setattr(wrapper, attr, value)

        wrapper.__dict__ |= getattr(wrapped, '__dict__', {})
        wrapper.__wrapped__ = wrapped  # pyright: ignore [reportFunctionMemberAccess]
        return wrapper

    return decorator


def package_to_anchor(
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

    @_wraps(func)
    def wrapper(
        anchor: _t.Optional[Anchor] = _undefined,
        package: _t.Optional[Anchor] = _undefined,
    ) -> abc.Traversable:
        # Base case:
        if (package is _undefined) and (anchor is not _undefined):
            return func(anchor)

        # Warning case:
        if (package is not _undefined) and (anchor is _undefined):
            warnings.warn(
                "First parameter to files is renamed to 'anchor'",
                DeprecationWarning,
                stacklevel=2,
            )
            return func(package)

        # Error cases:
        # Expected to raise TypeError.
        if (package is not _undefined) and (anchor is not _undefined):
            return func(anchor, package)  # pyright: ignore [reportCallIssue, reportUnknownVariableType]
        else:
            return func()  # pyright: ignore [reportCallIssue, reportUnknownVariableType]

    return wrapper


@package_to_anchor
def files(anchor: _t.Optional[Anchor] = None) -> abc.Traversable:
    """
    Get a Traversable resource for an anchor.
    """
    return from_package(resolve(anchor))


def resolve(cand: _t.Optional[Anchor]) -> _t.ModuleType:
    if cand is None:
        # Depth is 3 because: <caller>() (3) -> package_to_anchor (2) -> files (1) -> resolve (0).
        cand = _get_caller_module_name(depth=3)

    if isinstance(cand, str):
        return importlib.import_module(cand)
    else:
        # This allows non-modules through, but we rely on from_package() to catch such cases.
        return cand


def _get_caller_module_name(depth: int = 1, default: str = "__main__") -> str:
    """Find the module name of the frame one level beyond the depth given."""

    try:
        return sys._getframemodulename(depth + 1) or default  # pyright: ignore # noqa: PGH003 # Guarded.
    except AttributeError:  # For platforms without sys._getframemodulename().
        global _get_caller_module_name

        def _get_caller_module_name(depth: int = 1, default: str = "__main__") -> str:
            """Find the module name of the frame one level beyond the depth given."""

            try:
                return _get_frame(depth + 1).f_globals.get("__name__", default)  # pyright: ignore # noqa: PGH003 # Guarded.
            except (AttributeError, ValueError):  # For platforms without sys._getframe() or a steep enough call stack.
                global _get_caller_module_name

                def _get_caller_module_name(depth: int = 1, default: str = "__main__") -> str:
                    """Find the module name of the frame one level beyond the depth given."""

                    msg = "Cannot get the caller's module's name."
                    raise RuntimeError(msg)

                return _get_caller_module_name(depth, default)

        return _get_caller_module_name(depth, default)


def _get_frame(depth: int = 1, /) -> _t.Optional[_t.FrameType]:
    """Return the frame object for one of the caller's parent stack frames.

    Notes
    -----
    This attempts to support Python implementations that don't support sys._getframe(x) where x >= 2,
    e.g. Jython, IronPython.

    This avoids `inspect.stack()` because of how expensive `inspect` is to import.
    """

    try:
        return sys._getframe(depth + 1)
    except (AttributeError, ValueError):  # For platforms without sys._getframe().
        global _get_frame

        def _get_frame(depth: int = 1, /) -> _t.Optional[_t.FrameType]:
            """Return the frame object for the caller's parent stack frame."""

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
                        """Return the frame object for the caller's parent stack frame."""

                    return _get_frame()

        return _get_frame()


def from_package(package: _t.ModuleType) -> abc.Traversable:
    """Get the Traversable object for the given package."""

    spec = package.__spec__
    assert spec is not None

    reader = wrap_spec(spec)
    return reader.files()


def _check_dir_exists(path: abc.Traversable) -> bool:
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


def as_file(path: abc.Traversable) -> _t.AbstractContextManager[_l.pathlib.Path]:
    """
    Given a Traversable object, return that object as a
    path on the local file system in a context manager.
    """
    if isinstance(path, _l.pathlib.Path):
        return _AsFilePathContext(path)
    elif _check_dir_exists(path):
        return _TempDirContext(path)
    else:
        return _TempFileContext(path.read_bytes, suffix=path.name)


class _AsFilePathContext:
    """
    Degenerate behavior for pathlib.Path objects.
    """

    def __init__(self, path: _l.pathlib.Path, /):
        self.path = path

    def __enter__(self, /) -> _l.pathlib.Path:
        return self.path

    def __exit__(self, *_dont_care: object):
        pass


def _write_contents(target: _l.pathlib.Path, source: abc.Traversable) -> _l.pathlib.Path:
    child = target.joinpath(source.name)
    if source.is_dir():
        child.mkdir()
        for item in source.iterdir():
            _write_contents(child, item)
    else:
        child.write_bytes(source.read_bytes())
    return child


class _TempDirContext:
    """
    Given a traversable dir, recursively replicate the whole tree
    to the file system in a context manager.
    """

    def __init__(self, path: abc.Traversable, /):
        assert path.is_dir()
        self.path = path

    def __enter__(self, /):
        self.temp_dir = _l.tempfile.TemporaryDirectory()  # pyright: ignore [reportUninitializedInstanceVariable]
        temp_dir_path = _l.pathlib.Path(self.temp_dir.__enter__())
        return _write_contents(temp_dir_path, self.path)

    def __exit__(self, *exc_info: object):
        return self.temp_dir.__exit__(*exc_info)  # pyright: ignore [reportArgumentType]


class _TempFileContext:
    def __init__(
        self,
        reader: _t.Callable[[], bytes],
        suffix: str = '',
        # gh-93353: Keep a reference to call os.remove() in late Python
        # finalization.
        *,
        _os_remove: _t.Callable[[str], None] = os.remove,
    ):
        self.reader = reader
        self.suffix = suffix
        self.os_remove = _os_remove
        self.raw_path = ""

    def __enter__(self, /):
        # Not using tempfile.NamedTemporaryFile as it leads to deeper 'try'
        # blocks due to the need to close the temporary file to work on Windows
        # properly.
        fd, self.raw_path = _l.tempfile.mkstemp(suffix=self.suffix)
        try:
            os.write(fd, self.reader())
        finally:
            os.close(fd)
        del self.reader
        return _l.pathlib.Path(self.raw_path)

    def __exit__(self, *_dont_care: object):
        try:
            self.os_remove(self.raw_path)
        except FileNotFoundError:
            pass
