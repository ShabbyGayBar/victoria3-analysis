"""Parser for Victoria 3 localization files.

Victoria 3 localization is deliberately parsed as text rather than YAML.  The
game's markup (references, icons, and data functions) is useful to callers and
must therefore remain untouched.
"""

from pathlib import Path
import re
import warnings
from types import MappingProxyType
from typing import Final, Mapping

import pandas as pd

from vic3_analysis.utils import get_vic3_directory

_LANGUAGE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*$")
_ENTRY_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?P<key>[^\s:#]+)\s*:\s*" r'(?:\d+\s*)?"'
)
_CACHE: dict[tuple[Path, str], Mapping[str, str]] = {}


def _closing_quote(line: str, start: int) -> int | None:
    """Return the outer closing quote, tolerating Vic3's raw inner quotes."""
    for index in range(start, len(line)):
        if line[index] != '"':
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= start and line[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2:
            continue
        remainder = line[index + 1 :]
        if not remainder.strip() or remainder.lstrip().startswith("#"):
            return index
    return None


def _parse_file(path: Path, entries: dict[str, str]) -> None:
    """Read one localization file into *entries*, preserving source text."""
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.fullmatch(r"l_[a-z0-9_]+:", stripped):
            continue
        match = _ENTRY_PREFIX_RE.match(line)
        closing_quote = None if match is None else _closing_quote(line, match.end())
        if match is None or closing_quote is None:
            warnings.warn(
                f"Malformed localization entry at {path}:{line_number}",
                UserWarning,
                stacklevel=2,
            )
            continue
        entries[match.group("key")] = line[match.end() : closing_quote]


def _catalog(game_dir: Path, language: str) -> Mapping[str, str]:
    """Return the cached effective catalog for a game directory/language."""
    key = (game_dir.resolve(), language)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    language_dir = game_dir / "localization" / language
    if not language_dir.is_dir():
        raise ValueError(f"Unknown localization language: {language!r}")
    suffix = f"_l_{language}.yml"
    files = sorted(
        (p for p in language_dir.rglob("*.yml") if p.name.endswith(suffix)),
        key=lambda p: p.relative_to(language_dir).as_posix(),
        reverse=True,
    )
    ordinary = [p for p in files if "replace" not in p.relative_to(language_dir).parts]
    replacements = [p for p in files if "replace" in p.relative_to(language_dir).parts]
    entries: dict[str, str] = {}
    for path in (*ordinary, *replacements):
        _parse_file(path, entries)
    result = MappingProxyType(dict(sorted(entries.items())))
    _CACHE[key] = result
    return result


def _localization_values(
    language: str, game_dir: str | Path | None = None
) -> Mapping[str, str]:
    """Return the internal immutable catalog used by entity parsers."""
    if not isinstance(language, str) or not _LANGUAGE_RE.fullmatch(language):
        raise ValueError(f"Invalid localization language: {language!r}")
    root = get_vic3_directory() if game_dir is None else Path(game_dir)
    return _catalog(root, language)


def _insert_localization_column(
    frame: pd.DataFrame,
    source: str,
    target: str,
    values: Mapping[str, str],
) -> None:
    """Insert a nullable localization column after its identifier column."""
    localized = pd.Series(
        [values.get(str(item), pd.NA) for item in frame[source]],
        index=frame.index,
        dtype="string",
    )
    position = frame.columns.tolist().index(source) + 1
    frame.insert(position, target, localized)


def localization(language: str, game_dir: str | Path | None = None) -> pd.DataFrame:
    """Parse the effective Victoria 3 localization catalog.

    Values are raw quoted contents: game references, markup, and escape
    sequences are not expanded.  ``language`` is Victoria 3's internal name,
    such as ``"english"`` or ``"simp_chinese"``.
    """
    values = _localization_values(language, game_dir)
    return pd.DataFrame(values.items(), columns=["key", "localization"], dtype="string")


__all__ = ["localization"]
