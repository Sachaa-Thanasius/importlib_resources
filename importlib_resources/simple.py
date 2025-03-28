"""
Interface adapters for low-level readers.
"""

import abc
import io
from collections.abc import Iterator
from typing import Any, BinaryIO, Literal, TextIO, Union, overload

from ._typing_compat import StrPath
from .abc import Traversable, TraversableResources


__all__ = ['SimpleReader', 'ResourceHandle', 'ResourceContainer', 'TraversableReader']


class SimpleReader(abc.ABC):
    """
    The minimum, low-level interface required from a resource
    provider.
    """

    @property
    @abc.abstractmethod
    def package(self) -> str:
        """
        The name of the package for which this reader loads resources.
        """

    @abc.abstractmethod
    def children(self) -> list['SimpleReader']:
        """
        Obtain an iterable of SimpleReader for available
        child containers (e.g. directories).
        """

    @abc.abstractmethod
    def resources(self) -> list[str]:
        """
        Obtain available named resources for this virtual package.
        """

    @abc.abstractmethod
    def open_binary(self, resource: str) -> BinaryIO:
        """
        Obtain a File-like for a named resource.
        """

    @property
    def name(self) -> str:
        return self.package.split('.')[-1]


class ResourceContainer(Traversable):
    """
    Traversable container for a package's resources via its reader.
    """

    def __init__(self, reader: SimpleReader):
        self.reader = reader

    def is_dir(self) -> bool:
        return True

    def is_file(self) -> bool:
        return False

    def iterdir(self) -> Iterator[Union["ResourceHandle", "ResourceContainer"]]:
        for name in self.reader.resources():  # files
            yield ResourceHandle(self, name)
        for child in self.reader.children():  # dirs
            yield ResourceContainer(child)

    def open(self, *args: Any, **kwargs: Any) -> Any:
        raise IsADirectoryError

    @property
    def name(self) -> str:
        return self.reader.name


class ResourceHandle(Traversable):
    """
    Handle to a named resource in a ResourceReader.
    """

    def __init__(self, parent: ResourceContainer, name: str):
        self.parent = parent
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def is_file(self) -> bool:
        return True

    def is_dir(self) -> bool:
        return False

    @overload
    def open(self, mode: Literal['r'] = 'r', *args: Any, **kwargs: Any) -> TextIO: ...
    @overload
    def open(self, mode: Literal['rb'], *args: Any, **kwargs: Any) -> BinaryIO: ...
    def open(self, mode: str = 'r', *args: Any, **kwargs: Any) -> Union[TextIO, BinaryIO]:
        stream = self.parent.reader.open_binary(self.name)
        if 'b' not in mode:
            stream = io.TextIOWrapper(stream, *args, **kwargs)
        return stream

    def joinpath(self, *descendents: StrPath) -> Traversable:
        msg = "Cannot traverse into a resource"
        raise RuntimeError(msg)

    def iterdir(self) -> Iterator[Traversable]:
        msg = "Cannot traverse into a resource"
        raise RuntimeError(msg)


class TraversableReader(TraversableResources, SimpleReader):
    """
    A TraversableResources based on SimpleReader. Resource providers
    may derive from this class to provide the TraversableResources
    interface by supplying the SimpleReader interface.
    """

    def files(self) -> ResourceContainer:
        return ResourceContainer(self)
