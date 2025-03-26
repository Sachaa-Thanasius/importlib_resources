from __future__ import annotations

from importlib.machinery import ModuleSpec

from . import _lazy_modules as _l
from . import _typing_compat as _t


class CompatibilityFiles:
    """
    Adapter for an existing or non-existent resource reader
    to provide a compatibility .files().
    """

    def __init__(self, spec: ModuleSpec):
        self.spec: ModuleSpec = spec

    @property
    def _reader(self) -> _t.Optional[_l.abc.Traversable]:
        try:
            return self.spec.loader.get_resource_reader(self.spec.name)
        except AttributeError:
            pass

    def _native(self):
        """
        Return the native reader if it supports files().
        """
        reader = self._reader
        return reader if hasattr(reader, 'files') else self

    def __getattr__(self, attr: str, /) -> _t.Any:
        return getattr(self._reader, attr)

    def files(self) -> _l.abc.Traversable:
        from ._paths_compat import SpecPath

        return SpecPath(self.spec, self._reader)


class TraversableResourcesLoader:
    """
    Adapt a loader to provide TraversableResources.
    """

    def __init__(self, spec: ModuleSpec):
        self.spec = spec

    def get_resource_reader(self, name: str):
        return CompatibilityFiles(self.spec)._native()


class SpecLoaderAdapter:
    """
    Adapt a package spec to adapt the underlying loader.
    """

    def __init__(self, spec: ModuleSpec, adapter=lambda spec: spec.loader):
        self.spec = spec
        self.loader = adapter(spec)

    def __getattr__(self, name: str):
        return getattr(self.spec, name)


def wrap_spec(package: _t.ModuleType) -> SpecLoaderAdapter:
    """
    Construct a package spec with traversable compatibility
    on the spec/loader/reader.
    """
    return SpecLoaderAdapter(package.__spec__, TraversableResourcesLoader)
