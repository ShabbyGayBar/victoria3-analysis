# Victoria 3 Analysis

Python package for parsing and analyzing Victoria 3 game data.

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

## Architecture

- `src/vic3_analysis/parse/` - Parsers for game data files (buildings, goods, production methods, technology)
- `src/vic3_analysis/analysis/` - Production chain optimization via linear programming
- `tables/` - CSV output from example scripts
- `examples/` - Scripts that generate tables/*.csv

## Game Data Requirement

Parsers require Victoria 3 game files. The `get_vic3_directory()` function auto-detects Steam library paths on Windows/Linux/macOS. If auto-detection fails, pass `game_dir` explicitly to parsers:

```python
from vic3_analysis import BuildingsParser, production_table
parser = BuildingsParser(game_dir="/path/to/Victoria 3/game")
df = production_table(game_dir="/path/to/Victoria 3/game")
```

Tests require a local Victoria 3 installation.

## Key Entry Points

- `BuildingsParser()` - Parse building definitions
- `production_table()` - Build DataFrame of all building configurations
- `ProductionAnalyzer` - Filter and optimize production via linear programming
