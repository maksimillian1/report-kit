"""The refs a register's prose names — `M1 ÷ M2` in a source, "second opinion
on M1" in notes — checked against the registers that define them. A ref
cited by path, `00-baseline/M4`, is looked up in that sibling execution."""

from __future__ import annotations

import re
from pathlib import Path

from report_kit.register import REGISTER, Register, RegisterError, read_register

MENTION = re.compile(r"(?<![\w/])(?:(?P<execution>[\w.-]+)/)?(?P<ref>[MDRE][1-9]\d*)\b")


def mention_problems(register: Register) -> list[str]:
    defined = {register.path: {metric.ref for metric in register.metrics}}
    problems = []
    for metric in register.metrics:
        for text in (metric.source or "", metric.notes):
            for found in MENTION.finditer(text):
                problem = unknown(register, found, defined)
                if problem:
                    problems.append(f"{metric.ref} names {found.group()}, {problem}")
    return problems


def unknown(register: Register, found: re.Match,
            defined: dict[Path, set[str]]) -> str | None:
    path = (register.directory.parent / found["execution"] / REGISTER
            if found["execution"] else register.path)
    if path not in defined:
        try:
            defined[path] = {metric.ref for metric in read_register(path).metrics}
        except RegisterError as exc:
            return f"and {found['execution']} has no register to look in ({exc})"
    if found["ref"] in defined[path]:
        return None
    where = f"{found['execution']}'s register" if found["execution"] else "this register"
    return f"which {where} does not define"
