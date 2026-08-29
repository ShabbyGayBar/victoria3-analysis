# Test Conventions

## Location & Naming

- Tests live in `tests/`, one file per module under test, named `test_<module>.py`.
- Test functions are `test_*` (module-scoped); no test classes.
- `pyproject.toml` pins `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`.

## Toolchain

- Run with `uv run pytest` (coverage is auto-enabled via `addopts`: `--cov=src --cov-report=term-missing`).
- Lint tests with `uv run ruff check tests` and format with `uv run ruff format tests` — same config as `src`.
- Type-check tests with `uv run pyright` — `[tool.pyright]` in `pyproject.toml` includes both `src` and `tests`, so one command covers them.
- `--strict-markers` and `--strict-config` are on: never use unregistered markers or unknown config keys.

## Imports

- Import the public API from the top-level `vic3_analysis` package when re-exported there (e.g. `from vic3_analysis import goods, PopTypesParser, production_table`).
- Import internal symbols that are not re-exported from their full path (e.g. `from vic3_analysis.analysis.economy import Economy, EconomyState`).

## Game Data

- Tests run against a **local Victoria 3 installation** (auto-detected via `get_vic3_directory()`); there is no `conftest.py` and no mocking layer. Parsers/fixtures that need game files simply call the constructors with no `game_dir` argument.
- Expensive parsing (`production_table()`, `PopTypesParser()`, `goods()`) should be shared via a **module-scoped fixture** rather than re-parsing per test.

## Test Style

- **Function-based**, no `unittest.TestCase`.
- **Smoke tests** (call a function, assert it doesn't crash) are acceptable for thin parsers, but modules with real logic should assert on values, shapes, and columns.
- Prefer **deterministic synthetic inputs** for pure-logic units (e.g. `EconomyState` arithmetic): build the state directly with small numpy vectors and assert exact results with `pytest.approx` / `np.testing.assert_allclose`.
- For integration tests against game data, assert on **shapes, dtypes, index consistency, and column order** rather than brittle magic numbers.
- Validate `ValueError` branches with `pytest.raises(ValueError, match=<substring>)`.
- DataFrame equality: use `pd.testing.assert_frame_equal` (sort by a stable key and reset the index first to avoid order fragility).
- Array equality: use `np.testing.assert_array_equal` (exact) or `np.testing.assert_allclose` (float matmul results).

## Coverage

- Target **100% coverage** for the module under test (the `--cov=src` report surfaces missing lines). If a branch can't be covered, note why rather than leaving it untested.
