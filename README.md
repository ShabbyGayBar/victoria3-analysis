# Victoria 3 Analysis

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FShabbyGayBar%2Fvictoria3-analysis%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ShabbyGayBar/victoria3-analysis/ci.yml)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/71a4a3f3b6824b08a9e7c9fc8621f49a)](https://app.codacy.com/gh/ShabbyGayBar/victoria3-analysis/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)

This repository contains code for analyzing Victoria 3 game data. A pinned
submodule provides the separately licensed generated datasets and analytical
artifacts used by the documentation and examples.

## Features

### Data Parsing

Supports
- building
- pop_need
- goods
- production_method(_group)
- technology

information parsing from the game files and exporting into structured formats for analysis.

### Data Analysis

Supports
- Modelling and optimization of production chains based on the parsed data, allowing players to optimize their in-game production strategies.

## Installation

```bash
pip install "https://github.com/ShabbyGayBar/victoria3-analysis/releases/download/v0.1.0/vic3_analysis-0.1.0-py3-none-any.whl"
```

For development purposes, you can clone the repository and install the package in editable mode:

```bash
git clone --recurse-submodules https://github.com/ShabbyGayBar/victoria3-analysis.git
cd victoria3-analysis
uv sync
```

For an existing checkout, initialize the pinned artifact repository with:

```bash
git submodule update --init --recursive
```

## License

The original code, tests, examples, documentation, configuration, and
analytical methods in this repository are licensed under the
[GNU General Public License](LICENSE), version 3 or (at your option) any later
version, except where stated otherwise.

Generated data and analytical artifacts under `artifacts/datasets/` and
`artifacts/analyses/` are derived from Victoria 3 game content and are excluded
from the GPL license grant. The separate artifact repository's
[LICENSE](https://github.com/ShabbyGayBar/victoria3-analysis-artifacts/blob/main/LICENSE)
describes their provenance, applicable terms, and affiliation disclaimer.

Revisions published before the commit that introduced GPL-3.0-or-later remain
available under the MIT License terms that accompanied those revisions. This
license change does not revoke those existing grants.
