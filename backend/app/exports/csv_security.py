from __future__ import annotations


SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_spreadsheet_formula(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip(" \t\r\n").startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + value
    return value
