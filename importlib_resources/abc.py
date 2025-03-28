# NOTE: If this is being imported, there's no point delaying typing-related imports; it doesn't need ._typing.compat.

from __future__ import annotations

import abc

from . import _typing_compat as _t
from ._typing_compat import TYPE_CHECKING


__all__ = ["ResourceReader", "Traversable", "TraversableResources"]


if TYPE_CHECKING:
    from ._traversable import Traversable


def __getattr__(name: str) -> object:
    if name == "Traversable":
        from ._traversable import Traversable

        return Traversable

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


class ResourceReader(metaclass=abc.ABCMeta):
    """Abstract base class for loaders to provide resource reading support."""

    @abc.abstractmethod
    def open_resource(self, resource: str) -> _t.BinaryIO:
        """Return an opened, file-like object for binary reading.

        The 'resource' argument is expected to represent only a file name.
        If the resource cannot be found, FileNotFoundError is raised.
        """
        # This deliberately raises FileNotFoundError instead of
        # NotImplementedError so that if this method is accidentally called,
        # it'll still do the right thing.
        raise FileNotFoundError

    @abc.abstractmethod
    def resource_path(self, resource: str) -> str:
        """Return the file system path to the specified resource.

        The 'resource' argument is expected to represent only a file name.
        If the resource does not exist on the file system, raise
        FileNotFoundError.
        """
        # This deliberately raises FileNotFoundError instead of
        # NotImplementedError so that if this method is accidentally called,
        # it'll still do the right thing.
        raise FileNotFoundError

    @abc.abstractmethod
    def is_resource(self, path: str) -> bool:
        """Return True if the named 'path' is a resource.

        Files are resources, directories are not.
        """
        raise FileNotFoundError

    @abc.abstractmethod
    def contents(self) -> _t.Iterable[str]:
        """Return an iterable of entries in `package`."""
        raise FileNotFoundError


class TraversalError(Exception):
    pass


class TraversableResources(ResourceReader):
    """
    The required interface for providing traversable
    resources.
    """

    @abc.abstractmethod
    def files(self) -> Traversable:  # TODO: Make this annotation valid at runtime.
        """Return a Traversable object for the loaded package."""

    def open_resource(self, resource: _t.StrPath) -> _t.BinaryIO:
        return self.files().joinpath(resource).open('rb')

    def resource_path(self, resource: _t.Any) -> str:
        raise FileNotFoundError(resource)

    def is_resource(self, path: _t.StrPath) -> bool:
        return self.files().joinpath(path).is_file()

    def contents(self) -> _t.Iterator[str]:
        for item in self.files().iterdir():
            yield item.name
