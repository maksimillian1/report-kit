"""YAML read the way a registry needs it: a key written twice is an error."""

from __future__ import annotations

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    """`safe_load` keeps the last of two equal keys, so an entry defined twice
    loses its first definition without a word. Merge keys (`<<`) may still be
    overridden; only keys written out twice are refused."""

    def construct_mapping(self, node, deep=False):
        line_of: dict = {}
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=deep)
            line = key_node.start_mark.line + 1
            if key in line_of:
                raise yaml.constructor.ConstructorError(
                    None, None,
                    f"{key!r} appears twice, at lines {line_of[key]} and {line}",
                    key_node.start_mark)
            line_of[key] = line
        return super().construct_mapping(node, deep=deep)


def unknown_keys(mapping: dict, allowed: frozenset[str]) -> list[str]:
    return sorted(str(key) for key in mapping if key not in allowed)
