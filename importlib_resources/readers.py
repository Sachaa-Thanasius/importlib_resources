from __future__ import annotations

import itertools
import operator
import pathlib
import re
import warnings
import zipimport
from collections.abc import Generator, Iterable, Iterator
from typing import Any, BinaryIO, Optional, Protocol, TypeVar, Union

from . import _lazy_modules as _l
from . import abc
from ._typing_compat import StrPath
from .compat.py39 import ZipPath


_T = TypeVar("_T")
_U = TypeVar("_U")


__all__ = ['FileReader', 'ZipReader', 'MultiplexedPath', 'NamespaceReader']


def _remove_duplicates(items: Iterable[_T]) -> Iterator[_T]:
    return iter(dict.fromkeys(items))


# from more_itertools 9.0
def _only(
    iterable: Iterable[_T],
    default: _U = None,
    too_long: Optional[Union[Exception, type[Exception]]] = None,
) -> Union[_T, _U]:
    """If *iterable* has only one item, return it.
    If it has zero items, return *default*.
    If it has more than one item, raise the exception given by *too_long*,
    which is ``ValueError`` by default.
    >>> only([], default='missing')
    'missing'
    >>> only([1])
    1
    >>> only([1, 2])  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    ValueError: Expected exactly one item in iterable, but got 1, 2,
     and perhaps more.'
    >>> only([1, 2], too_long=TypeError)  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    TypeError
    Note that :func:`only` attempts to advance *iterable* twice to ensure there
    is only one item.  See :func:`spy` or :func:`peekable` to check
    iterable contents less destructively.
    """
    it = iter(iterable)
    first_value = next(it, default)

    try:
        second_value = next(it)
    except StopIteration:
        pass
    else:
        msg = f'Expected exactly one item in iterable, but got {first_value!r}, {second_value!r}, and perhaps more.'
        raise too_long or ValueError(msg)

    return first_value


class _HasPath(Protocol):
    path: _l.pathlib.Path


class FileReader(abc.TraversableResources):
    def __init__(self, loader: _HasPath):
        self.path = pathlib.Path(loader.path).parent

    def resource_path(self, resource: StrPath) -> str:
        """
        Return the file system path to prevent
        `resources.path()` from creating a temporary
        copy.
        """
        return str(self.path.joinpath(resource))

    def files(self) -> pathlib.Path:
        return self.path


class ZipReader(abc.TraversableResources):
    def __init__(self, loader: zipimport.zipimporter, module: str):
        self.prefix: str = loader.prefix.replace('\\', '/')
        if loader.is_package(module):
            _, _, name = module.rpartition('.')
            self.prefix += name + '/'
        self.archive: str = loader.archive

    def open_resource(self, resource: StrPath) -> BinaryIO:
        try:
            return super().open_resource(resource)
        except KeyError as exc:
            raise FileNotFoundError(exc.args[0]) from None

    def is_resource(self, path: StrPath) -> bool:
        """
        Workaround for `zipfile.Path.is_file` returning true
        for non-existent paths.
        """
        target = self.files().joinpath(path)  # pyright: ignore [reportUnknownMemberType] # zipp.Path's typing is lacking.
        return target.is_file() and target.exists()

    def files(self) -> ZipPath:  # pyright: ignore [reportIncompatibleMethodOverride] # zipp.Path's typing is lacking.
        return ZipPath(self.archive, self.prefix)


class MultiplexedPath(abc.Traversable):
    """
    Given a series of Traversable objects, implement a merged
    version of the interface across all objects. Useful for
    namespace packages which may be multihomed at a single
    name.
    """

    def __init__(self, *paths: abc.Traversable):
        self._paths = list(map(_ensure_traversable, _remove_duplicates(paths)))
        if not self._paths:
            message = 'MultiplexedPath must contain at least one path'
            raise FileNotFoundError(message)
        if not all(path.is_dir() for path in self._paths):
            msg = 'MultiplexedPath only supports directories'
            raise NotADirectoryError(msg)

    def iterdir(self) -> Iterator[abc.Traversable]:
        children = [child for path in self._paths for child in path.iterdir()]
        by_name = operator.attrgetter('name')
        groups = itertools.groupby(sorted(children, key=by_name), key=by_name)
        for _name, locs in groups:
            if (loc := self._follow(locs)) is not None:
                yield loc

    def read_bytes(self) -> bytes:
        msg = f'{self} is not a file'
        raise FileNotFoundError(msg)

    def read_text(self, *args: Any, **kwargs: Any) -> str:
        msg = f'{self} is not a file'
        raise FileNotFoundError(msg)

    def is_dir(self) -> bool:
        return True

    def is_file(self) -> bool:
        return False

    def joinpath(self, *descendants: StrPath) -> abc.Traversable:
        try:
            return super().joinpath(*descendants)
        except abc.TraversalError:
            # One of the paths did not resolve (a directory does not exist).
            # Just return something that will not exist.
            return self._paths[0].joinpath(*descendants)

    @classmethod
    def _follow(cls, children: Iterable[abc.Traversable]) -> Optional[abc.Traversable]:
        """
        Construct a MultiplexedPath if needed.

        If children contains a sole element, return it.
        Otherwise, return a MultiplexedPath of the items.
        Unless one of the items is not a Directory, then return the first.
        """
        subdirs, one_dir, one_file = itertools.tee(children, 3)

        try:
            return _only(one_dir)
        except ValueError:
            try:
                return cls(*subdirs)
            except NotADirectoryError:
                return next(one_file)

    def open(self, *args: Any, **kwargs: Any) -> Any:
        msg = f'{self} is not a file'
        raise FileNotFoundError(msg)

    @property
    def name(self) -> str:
        return self._paths[0].name

    def __repr__(self):
        paths = ', '.join(f"'{path}'" for path in self._paths)
        return f'MultiplexedPath({paths})'


class NamespaceReader(abc.TraversableResources):
    def __init__(self, namespace_path: Iterable[str]):
        # NOTE: A workaround until importlib._bootstrap._NamespacePath is exposed.
        if 'NamespacePath' not in str(namespace_path):
            msg = 'Invalid path'
            raise ValueError(msg)
        self.path = MultiplexedPath(*[part for part in map(self._resolve, namespace_path) if part is not None])

    @classmethod
    def _resolve(cls, path_str: str) -> abc.Traversable | None:
        r"""
        Given an item from a namespace path, resolve it to a Traversable.

        path_str might be a directory on the filesystem or a path to a
        zipfile plus the path within the zipfile, e.g. ``/foo/bar`` or
        ``/foo/baz.zip/inner_dir`` or ``foo\baz.zip\inner_dir\sub``.

        path_str might also be a sentinel used by editable packages to
        trigger other behaviors (see python/importlib_resources#311).
        In that case, return None.
        """
        dirs = (cand for cand in cls._candidate_paths(path_str) if cand.is_dir())
        return next(dirs, None)

    @classmethod
    def _candidate_paths(cls, path_str: str) -> Iterator[abc.Traversable]:
        yield pathlib.Path(path_str)
        yield from cls._resolve_zip_path(path_str)  # pyright: ignore [reportReturnType] # zipp.Path's typing is lacking.

    @staticmethod
    def _resolve_zip_path(path_str: str) -> Generator[ZipPath]:
        for match in reversed(list(re.finditer(r'[\\/]', path_str))):
            try:
                inner = path_str[match.end() :].replace('\\', '/') + '/'
                yield ZipPath(path_str[: match.start()], inner.lstrip('/'))
            except (  # noqa: PERF203
                FileNotFoundError,
                IsADirectoryError,
                NotADirectoryError,
                PermissionError,
            ):
                pass

    def resource_path(self, resource: StrPath) -> str:
        """
        Return the file system path to prevent
        `resources.path()` from creating a temporary
        copy.
        """
        return str(self.path.joinpath(resource))

    def files(self) -> MultiplexedPath:
        return self.path


def _ensure_traversable(path: Union[str, abc.Traversable]) -> abc.Traversable:
    """
    Convert deprecated string arguments to traversables (pathlib.Path).

    Remove with Python 3.15.
    """
    if not isinstance(path, str):
        return path

    warnings.warn(
        "String arguments are deprecated. Pass a Traversable instead.",
        DeprecationWarning,
        stacklevel=3,
    )

    return pathlib.Path(path)
