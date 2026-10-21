"""What a values command stops on."""

from __future__ import annotations


class RegistryError(Exception):
    """Anything the registry's own contents make impossible.

    Callers catch this one type and report it; they never have to know that
    underneath sit a YAML parser, an AST walk and a pile of file I/O.
    """
