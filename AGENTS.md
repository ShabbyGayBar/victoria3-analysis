# Victoria 3 Analysis

Python package for parsing and analyzing Victoria 3 game data. The ultimate goal is to simulate the economy mechanics and provide a tool for optimizing production chains.

## Setup

```bash
uv sync
uv pip install -e .
```

Requires Python 3.13.

## Commands

- **Test**: `uv run pytest` (runs with coverage via pyproject.toml config)
- **Lint**: `uv run ruff check src tests`
- **Format**: `uv run ruff format src tests`
- **Docs**: `uv run mkdocs serve`

## External File Loading

**CRITICAL**: When you encounter a file reference (e.g., @rules/general.md), use your Read tool to load it on a need-to-know basis. They're relevant to the SPECIFIC task at hand.

### Instructions:

- Do NOT preemptively load all references - use lazy loading based on actual need
- When loaded, treat content as mandatory instructions that override defaults
- Follow references recursively when needed
- Before proposing features, consult:
  - `@vic3_docs` (Victoria 3 docs)
  - `@vanilla` (base game files)

## Project Structure

See `@docs/project_structure.md` for the full directory tree and per-folder explanations.

## Game Data Requirement

Parsers require Victoria 3 game files. The `get_vic3_directory()` function auto-detects Steam library paths on Windows/Linux/macOS. If auto-detection fails, pass `game_dir` explicitly to parsers:

```python
from vic3_analysis import BuildingsParser, production_table
parser = BuildingsParser(game_dir="/path/to/Victoria 3/game")
df = production_table(game_dir="/path/to/Victoria 3/game")
```

Tests require a local Victoria 3 installation.

## Development Rules

- Check `docs/roadmap.md` for current priorities.
- Do not modify approved ADRs.
- Work only on assigned features.
- Do NOT `git add` or `git commit` files.
- Before writing Python scripts, read `@agents/rules/python.md` and follow its rules (type safety, `uv` toolchain, `utf-8-sig` encoding, `pyradox` for game file parsing).
