#!/usr/bin/env python3
# pylint: disable=protected-access
"""Static checks that guard against regressing lint suppressions."""

from __future__ import annotations

import re
from pathlib import Path

BANNED_PYLINT_CODES = {
    "unused-argument",
    "redefined-outer-name",
    "import-outside-toplevel",
    "unused-variable",
    "missing-type-doc",
    "missing-return-type-doc",
}

PYLINT_DISABLE_PATTERN = re.compile(r"#\s*pylint:\s*disable=([^\n]+)")
TYPE_IGNORE_REGEX = re.compile(r"#\s*type:\s*ignore(?!\[)")


def _iter_test_files() -> list[Path]:
    """Return all test modules except this guard."""
    tests_root = Path(__file__).resolve().parent
    guard_path = Path(__file__).resolve()
    return [
        file_path
        for file_path in tests_root.rglob("*.py")
        if file_path != guard_path
    ]


def test_banned_pylint_codes_absent() -> None:
    """Ensure banned pylint disable codes are not used in tests."""
    offenders: list[tuple[Path, list[str]]] = []

    for file_path in _iter_test_files():
        content = file_path.read_text(encoding="utf-8")
        for match in PYLINT_DISABLE_PATTERN.finditer(content):
            codes = [
                code.strip()
                for code in match.group(1).split(",")
                if code.strip()
            ]
            bad_codes = sorted(
                {code for code in codes if code in BANNED_PYLINT_CODES})
            if bad_codes:
                offenders.append((file_path, bad_codes))

    assert not offenders, f"Found banned pylint disables: {offenders}"


def test_type_ignore_annotations_absent() -> None:
    """Ensure generic type: ignore suppressions are avoided."""
    offenders: list[tuple[Path, int]] = []

    for file_path in _iter_test_files():
        for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
            if TYPE_IGNORE_REGEX.search(line):
                offenders.append((file_path, line_number))

    assert not offenders, f"Found '# type: ignore' usage at: {offenders}"
