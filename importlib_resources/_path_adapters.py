from __future__ import annotations

import importlib.machinery
from io import TextIOWrapper

from . import _lazy as _t
from . import abc


def _io_wrapper(
    file: _t.BinaryIO,
    mode: _t.Literal['r', 'rb'] = 'r',
    *args: _t.Any,
    **kwargs: _t.Any,
) -> _t.Union[_t.TextIO, _t.BinaryIO]:
    if mode == 'r':
        return TextIOWrapper(file, *args, **kwargs)

    if mode == 'rb':
        return file

    msg = f"Invalid mode value '{mode}', only 'r' and 'rb' are supported"
    raise ValueError(msg)


class OrphanPath(abc.Traversable):
    """
    Orphan path, not tied to a module spec or resource reader.
    Can't be read and doesn't expose any meaningful children.
    """

    def __init__(self, *path_parts: str):
        if len(path_parts) < 1:
            msg = 'Need at least one path part to construct a path'
            raise ValueError(msg)
        self._path = path_parts

    def iterdir(self) -> _t.Iterator[abc.Traversable]:
        return
        yield

    def is_file(self) -> bool:
        return False

    is_dir = is_file

    def joinpath(self, other: str) -> abc.Traversable:
        return OrphanPath(*self._path, other)

    @property
    def name(self) -> str:
        return self._path[-1]

    def open(self, mode: str = 'r', *args: _t.Any, **kwargs: _t.Any) -> _t.NoReturn:
        msg = "Can't open orphan path"
        raise FileNotFoundError(msg)


class ChildPath(abc.Traversable):
    """
    Path tied to a resource reader child.
    Can be read but doesn't expose any meaningful children.
    """

    def __init__(self, reader: abc.TraversableResources, name: str):
        self._reader = reader
        self._name = name

    def iterdir(self) -> _t.Iterator[abc.Traversable]:
        return iter(())

    def is_file(self) -> bool:
        return self._reader.is_resource(self.name)

    def is_dir(self) -> bool:
        return not self.is_file()

    def joinpath(self, other: str) -> abc.Traversable:
        return OrphanPath(self.name, other)

    @property
    def name(self) -> str:
        return self._name

    @_t.overload
    def open(self, mode: _t.Literal['r'] = 'r', *args: _t.Any, **kwargs: _t.Any) -> _t.TextIO: ...
    @_t.overload
    def open(self, mode: _t.Literal['rb'], *args: _t.Any, **kwargs: _t.Any) -> _t.BinaryIO: ...
    def open(
        self, mode: _t.Literal['r', 'rb'] = 'r', *args: _t.Any, **kwargs: _t.Any
    ) -> _t.Union[_t.TextIO, _t.BinaryIO]:
        return _io_wrapper(self._reader.open_resource(self.name), mode, *args, **kwargs)


class SpecPath(abc.Traversable):
    """
    Path tied to a module spec.
    Can be read and exposes the resource reader children.
    """

    def __init__(self, spec: importlib.machinery.ModuleSpec, reader: _t.Optional[abc.TraversableResources]):
        self._spec = spec
        self._reader = reader

    def iterdir(self) -> _t.Iterator[abc.Traversable]:
        if not self._reader:
            return
        for path in self._reader.contents():
            yield ChildPath(self._reader, path)

    def is_file(self) -> bool:
        return False

    is_dir = is_file

    def joinpath(self, other: str) -> abc.Traversable:
        if not self._reader:
            return OrphanPath(other)
        return ChildPath(self._reader, other)

    @property
    def name(self) -> str:
        return self._spec.name

    @_t.overload
    def open(self, mode: _t.Literal['r'] = 'r', *args: _t.Any, **kwargs: _t.Any) -> _t.TextIO: ...
    @_t.overload
    def open(self, mode: _t.Literal['rb'], *args: _t.Any, **kwargs: _t.Any) -> _t.BinaryIO: ...
    def open(
        self, mode: _t.Literal['r', 'rb'] = 'r', *args: _t.Any, **kwargs: _t.Any
    ) -> _t.Union[_t.TextIO, _t.BinaryIO]:
        return _io_wrapper(self._reader.open_resource(None), mode, *args, **kwargs)
