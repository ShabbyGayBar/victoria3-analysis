# Production Optimization

This is my main purpose for creating this project.

The optimization is implemented in the `NominalOptimizer` class, using linear programming and other optimization functions provided by the `scipy` library.

The method responsible for performing the optimization is `linprog()`, which returns an `EconomyState` containing the optimal building levels and their corresponding economy state.

To perform a production optimization, we must first acquire the following:

+ An `Economy` instance, which wraps the production table, goods table, and pop-types table parsed from the Victoria 3 game files. The `NominalOptimizer` is constructed with an `Economy` and derives per-building vectors (GDP, employment, construction cost, goods flows) from it.

+ An objective, set via `set_objective()`. Named objectives include `"gdp"` (maximise gross GDP), `"employment"` (maximise total employment), and `"construction_cost"` (minimise total construction cost). For custom objectives, you can set `objective_vector` directly to any `*_vector()` result (e.g. `employment_vector()` to *minimise* employment).

+ Constraints, added incrementally via the fluent `constraint_*` methods. For example, if you want to ensure that your economy must be self-sufficient, i.e., does not import any goods, call `constraint_limit_import(limit=0)`. Or if you want to ensure that your economy produces at least 100 units of steel, call `constraint_produce('steel', 100)`. All constraint methods start with `constraint_`, append to the optimizer's constraint lists, and return `self` for chaining.

When calling the `linprog()` method, no arguments are needed — the objective vector and constraints are already stored on the `NominalOptimizer` instance. The `linprog()` method will automatically combine the constraints into the format required by the `scipy` library.

Say you want to know what building combination can produce at least 100 units of steel with the least population. In this case, the objective vector is `employment_vector()`, since the population is represented by the employment in the production table. The constraint is `constraint_produce('steel', 100)` and `constraint_limit_import(0)`. The code for this optimization is as follows:

```python
from vic3_analysis import Economy, NominalOptimizer

economy = Economy()
optimizer = NominalOptimizer(economy)
optimizer.objective_vector = optimizer.employment_vector()
optimizer.constraint_produce("steel", 100)
optimizer.constraint_limit_import(0)
state = optimizer.linprog()

import numpy as np
annual_gdp = float(np.dot(state.building_levels, optimizer.gdp_vector())) * 52
employment = float(np.sum(state.pops))
construction_cost = economy.construction_cost(state)
print(f"GDP: {annual_gdp}")
print(f"Employment: {employment}")
print(f"Construction Cost: {construction_cost}")
print(economy.df_buildings(state))
```
