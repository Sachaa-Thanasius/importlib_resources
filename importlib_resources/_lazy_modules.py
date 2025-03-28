"""Middleman for modules that need to be lazily imported.

Usually, these are modules that are expensive to import but likely aren't needed until runtime, and possibly not even
then.
"""

__all__ = (
    # stdlib modules
    "pathlib",
    "tempfile",
    # sibling modules
    "readers",
)


def __getattr__(name: str) -> object:
    if name == "pathlib":
        global pathlib

        import pathlib

        return pathlib

    if name == "tempfile":
        global tempfile

        import tempfile

        return tempfile

    if name == "readers":
        global readers

        from . import readers

        return readers

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    return sorted(globals().keys() | __all__)
