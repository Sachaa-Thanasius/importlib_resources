from __future__ import annotations

from importlib.machinery import ModuleSpec
from io import TextIOWrapper

from . import _lazy_modules as _l
from . import _typing_compat as _t
from . import abc


def _io_wrapper(file, mode: str = 'r', *args: _t.Any, **kwargs: _t.Any):
    if mode == 'r':
        return TextIOWrapper(file, *args, **kwargs)

    if mode == 'rb':
        return file

    msg = f"Invalid mode value '{mode}', only 'r' and 'rb' are supported"
    raise ValueError(msg)


class SpecPath(abc.Traversable):
    """
    Path tied to a module spec.
    Can be read and exposes the resource reader children.
    """

    def __init__(self, spec: ModuleSpec, reader: _t.Optional[_l.abc.Traversable]):
        self._spec = spec
        self._reader = reader

    def iterdir(self):
        if not self._reader:
            return
        for path in self._reader.contents():
            yield ChildPath(self._reader, path)

    def is_file(self) -> bool:
        return False

    is_dir = is_file

    def joinpath(self, other):
        if not self._reader:
            return OrphanPath(other)
        return ChildPath(self._reader, other)

    @property
    def name(self):
        return self._spec.name

    def open(self, mode: str = 'r', *args: _t.Any, **kwargs: _t.Any):
        return _io_wrapper(self._reader.open_resource(None), mode, *args, **kwargs)


class ChildPath(abc.Traversable):
    """
    Path tied to a resource reader child.
    Can be read but doesn't expose any meaningful children.
    """

    def __init__(self, reader, name):
        self._reader = reader
        self._name = name

    def iterdir(self):
        return iter(())

    def is_file(self):
        return self._reader.is_resource(self.name)

    def is_dir(self):
        return not self.is_file()

    def joinpath(self, other):
        return OrphanPath(self.name, other)

    @property
    def name(self) -> str:
        return self._name

    def open(self, mode: str = 'r', *args: _t.Any, **kwargs: _t.Any):
        return _io_wrapper(self._reader.open_resource(self.name), mode, *args, **kwargs)


class OrphanPath(abc.Traversable):
    """
    Orphan path, not tied to a module spec or resource reader.
    Can't be read and doesn't expose any meaningful children.
    """

    def __init__(self, *path_parts):
        if len(path_parts) < 1:
            msg = 'Need at least one path part to construct a path'
            raise ValueError(msg)
        self._path = path_parts

    def iterdir(self):
        return iter(())

    def is_file(self) -> bool:
        return False

    is_dir = is_file

    def joinpath(self, other):
        return OrphanPath(*self._path, other)

    @property
    def name(self) -> str:
        return self._path[-1]

    def open(self, mode: str = 'r', *args: _t.Any, **kwargs: _t.Any):
        msg = "Can't open orphan path"
        raise FileNotFoundError(msg)
