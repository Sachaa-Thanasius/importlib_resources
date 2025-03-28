from __future__ import annotations

from importlib.machinery import ModuleSpec

from . import _common, abc
from . import _lazy as _l
from . import _lazy as _t


_ResourceReaderGetter: _t.TypeAlias = "_t.Callable[[str], _t.Optional[abc.TraversableResources]]"


def _block_standard(reader_getter: _ResourceReaderGetter) -> _ResourceReaderGetter:
    """
    Wrap TraversableResourcesLoader._regular_get_resource_reader()
    and intercept any standard library readers.
    """

    @_common._wraps(reader_getter)
    def wrapper(*args: _t.Any, **kwargs: _t.Any) -> _t.Optional[abc.TraversableResources]:
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
        if isinstance(reader, CompatibilityFiles) and reader.spec.loader.__class__.__module__.startswith((
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
    is_degenerate = isinstance(reader, CompatibilityFiles) and not reader._reader
    return reader if not is_degenerate else None


class CompatibilityFiles:
    """
    Adapter for an existing or non-existent resource reader
    to provide a compatibility .files().
    """

    def __init__(self, spec: ModuleSpec):
        self.spec: ModuleSpec = spec

    @property
    def _reader(self) -> _t.Optional[abc.TraversableResources]:
        try:
            return self.spec.loader.get_resource_reader(self.spec.name)
        except AttributeError:
            pass

    def _native(self) -> _t.Union[abc.TraversableResources, CompatibilityFiles]:
        """
        Return the native reader if it supports files().
        """
        reader = self._reader
        return reader if (reader is not None and hasattr(reader, 'files')) else self

    def __getattr__(self, attr: str, /) -> _t.Any:
        return getattr(self._reader, attr)

    def files(self) -> abc.Traversable:
        from ._path_adapters import SpecPath

        return SpecPath(self.spec, self._reader)


class TraversableResourcesLoader:
    """
    Adapt a loader to provide TraversableResources and other
    compatibility.

    Ensures the readers from importlib_resources are preferred
    over stdlib readers.
    """

    def __init__(self, spec: ModuleSpec):
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

    def _regular_get_resource_reader(self, name: str) -> abc.TraversableResources:
        # CompatabilityFiles provides .files(), which is all wrap_spec() needs.
        return CompatibilityFiles(self.spec)._native()  # pyright: ignore [reportReturnType]

    def get_resource_reader(self, name: str) -> abc.TraversableResources:
        return (
            _skip_degenerate(_block_standard(self._regular_get_resource_reader)(name))
            or self._standard_reader()
            or self._regular_get_resource_reader(name)
        )


def wrap_spec(spec: ModuleSpec) -> abc.TraversableResources:
    """
    Get the traversable resources reader for a module spec while wrapping missing functionality on the
    spec/loader/reader for compatability.
    """

    # Backwards compat: Shim a missing loader.
    loader = spec.loader
    if loader is None:
        loader = TraversableResourcesLoader(spec)

    # Backwards compat: Shim a missing get_resource_reader method.
    try:
        get_resource_reader = getattr(loader, "get_resource_reader")  # noqa: B009
    except AttributeError:

        def get_resource_reader(name: str) -> abc.TraversableResources:
            return CompatibilityFiles(spec)._native()  # pyright: ignore [reportReturnType]

    # Backwards compat: Shim a missing files method.
    reader = get_resource_reader(spec.name)
    if not hasattr(reader, "files"):
        reader = CompatibilityFiles(spec)

    return reader  # pyright: ignore [reportReturnType]
