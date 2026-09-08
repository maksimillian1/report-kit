from __future__ import annotations

import re
from pathlib import Path

# Windows-illegal characters plus control bytes and the path separators —
# what has to go before a string coming from data (a title, a tenant name, a
# URL segment) can be used as a filename.
ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

TOKEN = re.compile(r"\{(\w+)\}")


def fill(template: str, values: dict) -> str:
    """Replace `{name}` tokens, leaving every other brace alone.

    Not str.format(): the strings this fills are PromQL queries and shell
    command templates, which contain braces of their own — a label matcher
    like {namespace="x"} makes str.format() raise on the first one that
    isn't a bare identifier. Only `{bare_identifier}` is substituted here.

    Raises KeyError(name) for an unknown token — a silently unsubstituted
    placeholder ends up in a command line or a query, where it fails much
    later and much less clearly."""
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise KeyError(name)
        return str(values[name])
    return TOKEN.sub(replace, template)


def safe_filename(name: str, fallback: str, suffix: str = "",
                  max_len: int = 200) -> str:
    """Turn arbitrary text into a filename: strip any path components, replace
    illegal characters, optionally enforce a suffix, cap the length.

    `suffix` is off by default — a generic sanitizer has no business guessing
    the file type. Pass e.g. ".pdf" when the caller knows it."""
    name = Path(name or fallback).name.strip() or fallback
    name = ILLEGAL.sub("_", name)
    if suffix and not name.lower().endswith(suffix.lower()):
        name += suffix
    if len(name) > max_len:
        name = name[:max_len - len(suffix)] + suffix
    return name
