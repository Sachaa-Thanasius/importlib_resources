from __future__ import annotations

from .. import _adapters, _common  # noqa: TID252
from .. import _lazy_modules as _l  # noqa: TID252
from .. import _typing_compat as _t  # noqa: TID252


def _block_standard(reader_getter):
    """
    Wrap _adapters.TraversableResourcesLoader.get_resource_reader
    and intercept any standard library readers.
    """

    @_common._wraps(reader_getter)
    def wrapper(*args, **kwargs):
        """
        If the reader is from the standard library, return None to allow
        allow likely newer implementations in this library to take precedence.
        """
        try:
            reader = reader_getter(*args, **kwargs)
        except NotADirectoryError:
            # MultiplexedPath may fail on zip subdirectory
            return
        except ValueError as exc:
            # NamespaceReader in stdlib may fail for editable installs
            # (python/importlib_resources#311, python/importlib_resources#318)
            # Remove after bugfix applied to Python 3.13.
            if "not enough values to unpack" not in str(exc):
                raise
            return
        # Python 3.10+
        mod_name = reader.__class__.__module__
        if mod_name.startswith('importlib.') and mod_name.endswith('readers'):
            return
        # Python 3.8, 3.9
        if isinstance(reader, _adapters.CompatibilityFiles) and (
            reader.spec.loader.__class__.__module__.startswith('zipimport')
            or reader.spec.loader.__class__.__module__.startswith('_frozen_importlib_external')
        ):
            return
        return reader

    return wrapper


def _skip_degenerate(reader):
    """
    Mask any degenerate reader. Ref #298.
    """
    is_degenerate = isinstance(reader, _adapters.CompatibilityFiles) and not reader._reader
    return reader if not is_degenerate else None


class TraversableResourcesLoader(_adapters.TraversableResourcesLoader):
    """
    Adapt loaders to provide TraversableResources and other
    compatibility.

    Ensures the readers from importlib_resources are preferred
    over stdlib readers.
    """

    def get_resource_reader(self, name: str):
        return (
            _skip_degenerate(_block_standard(super().get_resource_reader)(name))
            or self._standard_reader()
            or super().get_resource_reader(name)
        )

    def _standard_reader(self):
        return self._zip_reader() or self._namespace_reader() or self._file_reader()

    def _zip_reader(self) -> _t.Optional[_l.readers.ZipReader]:
        try:
            return _l.readers.ZipReader(self.spec.loader, self.spec.name)
        except AttributeError:
            pass

    def _namespace_reader(self) -> _t.Optional[_l.readers.NamespaceReader]:
        try:
            return _l.readers.NamespaceReader(self.spec.submodule_search_locations)
        except (AttributeError, ValueError):
            pass

    def _file_reader(self) -> _t.Optional[_l.readers.FileReader]:
        try:
            path = _l.pathlib.Path(self.spec.origin)
        except TypeError:
            return None

        if path.exists():
            return _l.readers.FileReader(_t.SimpleNamespace(path=path))
        else:
            return None


def wrap_spec(package: _t.ModuleType) -> _adapters.SpecLoaderAdapter:
    """
    Override _adapters.wrap_spec to use TraversableResourcesLoader
    from above. Ensures that future behavior is always available on older
    Pythons.
    """
    return _adapters.SpecLoaderAdapter(package.__spec__, TraversableResourcesLoader)
