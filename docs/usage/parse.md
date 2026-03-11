# Data Parsing

For non-technical users, you can simply refer to the [parsed tables](https://github.com/ShabbyGayBar/victoria3-analysis/tree/main/tables) in the GitHub repository.

These tables are updated regularly and includes:

- `buildings.csv`: building information, including building groups, construction costs, unlocking technologies, and more.

- `buy_packages.csv`: pop political power and buying needs for each wealth level.

- `goods.csv`: goods information, including base price, obsession chance, etc.

- `production_methods.csv`: production method information, including input and output goods, production method groups, etc.

- `production_table.csv`: all combinations of production methods for each type of building, including the input and output goods, construction costs, and more. This table is also used for production optimization.

- `technology.csv`: technology information, including category, era, etc.

If you want to parse the data yourself, you can refer to the [`examples/` directory](https://github.com/ShabbyGayBar/victoria3-analysis/tree/main/examples) in the GitHub repository, which contains example scripts for parsing the data. The script name corresponds to the table name, e.g., `buildings.py` for parsing the `buildings.csv` table.
