# Victoria 3 Analysis

![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FShabbyGayBar%2Fvictoria3-analysis%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)

![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ShabbyGayBar/victoria3-analysis/ci.yml)

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/71a4a3f3b6824b08a9e7c9fc8621f49a)](https://app.codacy.com/gh/ShabbyGayBar/victoria3-analysis/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)

This repository contains code and data for analyzing Victoria 3 game data. It is intended to parse game data into csv or other structured formats, and provide insights into the game's mechanics and player strategies, such as production optimization.

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
git clone https://github.com/ShabbyGayBar/victoria3-analysis.git
cd victoria3-analysis
uv sync
uv pip install -e .
```

## License

This project is licensed under the MIT License.
