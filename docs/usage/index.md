# Usage

## Data Parsing

For non-technical users, you can simply refer to the [parsed tables](https://github.com/ShabbyGayBar/victoria3-analysis/tree/main/tables) in the GitHub repository. These tables are updated regularly and includes:
- `buildings.csv`: building information, including building groups, construction costs, unlocking technologies, and more.
- `buy_packages.csv`: pop political power and buying needs for each wealth level.
- `goods.csv`: goods information, including base price, obsession chance, etc.
- `production_methods.csv`: production method information, including input and output goods, production method groups, etc.
- `production_table.csv`: all combinations of production methods for each type of building, including the input and output goods, construction costs, and more. This table is also used for production optimization.
- `technology.csv`: technology information, including category, era, etc.

If you want to parse the data yourself, you can refer to the [`examples/` directory](https://github.com/ShabbyGayBar/victoria3-analysis/tree/main/examples) in the GitHub repository, which contains example scripts for parsing the data. The script name corresponds to the table name, e.g., `buildings.py` for parsing the `buildings.csv` table.

## Production Optimization

This is my main purpose for creating this project.

The optimization is implemented in the `ProductionAnalyzer` class, using linear programming and other optimization functions provided by the `scipy` library.

The method responsible for performing the optimization is `linprog()`, which returns a result dataframe containing the optimal building levels and their corresponding production methods.

To perform a production optimization, we must first acquire the following:
+ A `production_table` containing all possible buildings with different settings of production methods, which is already provided when calling the `ProductionAnalyzer` constructor.
+ An objective vector, which serves as a function representing the objective value you want to minimize. For example, if you want to minimize the total construction cost, the objective vector should be `construction_cost_vector()` of the `ProductionAnalyzer` instance. All objective vector functions provided by the `ProductionAnalyzer` instance ends with `_vector()`, and the name before `_vector()` indicates the objective value it represents.
+ Constraints representing the constraints of the optimization problem. For example, if you want to ensure that your economy must be self-sufficient, i.e., does not import any goods, the constraint should be `constraint_limit_import(limit=0)` of the `ProductionAnalyzer` instance. Or if you want to ensure that your economy produces at least 100 units of steel, the constraint should be `constraint_produce(good='steel', min_production=100)` of the `ProductionAnalyzer` instance. All constraint functions provided by the `ProductionAnalyzer` instance starts with `constraint_`, and the name after `constraint_` indicates the type of constraint it represents.

When calling the `linprog()` method, the `production_table` is omitted since it is already in the `ProductionAnalyzer` instance. The objective vector is passed as the first argument. The constraints are passed as a list, since usually there are multiple constraints in a production optimization problem. The `linprog()` method will automatically combine the constraints into the format required by the `scipy` library.

Say you want to know what building combination can produce at least 100 units of steel with the least population. In this case, the objective vector is `employment_vector()`, since the population is represented by the employment in the production table. The constraint is `constraint_produce('steel',100)` and `constraint_limit_import(0)`. The code for this optimization is as follows:

```python
from vic3_analysis import ProductionAnalyzer
analyzer = ProductionAnalyzer()
objective_vector = analyzer.employment_vector()
constraints = []
constraints.append(analyzer.constraint_produce('steel', 100))
constraints.append(analyzer.constraint_limit_import(0))
result = analyzer.linprog(objective_vector, constraints)
print(result)
```
