---
title: Optimization
description: Define objectives and constraints, optimize production scenarios, and apply state-region limits.
---

# Optimization

Mathematical Programming is the foundation of analyzing and optimizing Victoria 3's economy. The `vic3_analysis` package provides optimizers that choose building levels, which maximize or minimize the objective, for an `Economy` according to a scenario's constraints. Start with an economy model:

```python
from vic3_analysis import Economy

economy = Economy()
```

See the [economy guide](economy.md) for model construction and direct solving,
and the [economy-report dictionary](../data-dictionary/economy.md) for returned
state columns, formulas, and units.

## Scenario definition

Objective and constraints are defined in an immutable `Scenario` dataclass. Create a new scenario to change its assumptions.

- Use game script keys when setting attributes of `Scenario`, such as `"steel"` or `"building_steel_mills"`, rather than localized display names.
- Fields containing pairs use tuples such as `(("steel", 100.0),)`
- Fields containing only keys use tuples such as `("pm_diesel_engines",)`.
- An empty tuple `()` adds no entries.
- Optional caps default to `None`, which leaves that constraint disabled.
- The decision variables are non-negative, continuous (Fractional levels are allowed) building levels for each production configuration.
- Use weekly flows when setting goods quantities
- Employment is the workforce headcount, excluding dependents.

### Scenario name

| Attribute | Default | Meaning |
| --- | --- | --- |
| `name` | `None` | Optional label for the experiment; it does not affect the solution. `display_name()` returns this label, otherwise joins the `min_goods_output` good keys with `+`, or returns `"unnamed"` when there are no targets. |

### Objectives

The `objective` attribute defaults to `"automation"`. Its supported values are:

| Objective | Direction | Meaning | Optimizer |
| --- | --- | --- | --- |
| `gdp` | maximize | Model GDP: net goods output valued at base prices with `NominalOptimizer`, or endogenous market prices with `MarketOptimizer` and `EquilibriumOptimizer`. | All three |
| `gdp_per_capita` | maximize | Market-price GDP divided by workers plus dependents. | Market and equilibrium |
| `average_wealth` | maximize | Population-weighted household wealth tier, equal to employment-weighted wealth under the uniform workforce ratio. | Equilibrium only |
| `employment` | maximize | Total employed population. | Nominal only |
| `automation` | minimize | Employment required to satisfy the constraints. | Nominal only |
| `construction_cost` | minimize | Total construction cost required to satisfy the constraints. | Nominal only |

### Constraints

#### Production targets and market orders

| Attribute | Default | Meaning |
| --- | --- | --- |
| `min_goods_output` | `()` | `(good, amount)` pairs setting minimum weekly **net domestic output** after production inputs are deducted. For example, `(("steel", 100.0),)` requires at least 100 steel per week. Explicit entries override `default_min_goods_output` for those goods; negative amounts allow deficits. Imports, exports, and pop consumption are excluded from this net output. |
| `default_min_goods_output` | `0.0` | Minimum weekly net domestic output for each good without an explicit `min_goods_output` entry. The default, `0.0`, requires nonnegative net output; `-10.0` permits net output down to −10 per unspecified good. `None` leaves unspecified goods unconstrained and is required by `MarketOptimizer`. This field does not set fixed import orders. |
| `goods_trade_flow` | `()` | Fixed weekly `(good, amount)` pairs: positive imports add sell orders, negative exports add buy orders. These affect market prices and are not optimized. Add a `min_goods_output` target separately when domestic production must cover exports. |
| `pop_needs` | `()` | Fixed `(good, amount)` weekly population-consumption orders, added to market buy orders. Supply quantities by good, such as `(("grain", 200.0),)`, rather than pop-need category keys. These orders do not enforce a domestic production requirement. Must remain empty with `EquilibriumOptimizer`, which calculates household demand. |
| `workforce_ratio` | `1.0` | Uniform workers / total population in `(0, 1]`, retained in returned states. Employment caps count workers. Market GDP per capita and its gradient scale by this ratio; equilibrium also uses it for dependent consumption and earnings. |

`goods_trade_flow` and `pop_needs` require known good keys and finite amounts.
Trade quantities are signed; population orders must be non-negative. Repeated
entries for the same good are summed, but trade entries with opposing signs
are rejected: each good can only be imported or exported in this model. They do
not alter the nominal optimizer's objective or constraints, but are passed to
the returned economy state. The market optimizer uses them to calculate
prices, without requiring buy and sell orders to balance.

For example, `min_goods_output=(("steel", -20.0),)` with
`default_min_goods_output=0.0` allows a steel deficit of up to 20 units per
week while requiring nonnegative net output for every other good.

#### Available configurations and throughput

| Attribute | Default | Meaning |
| --- | --- | --- |
| `banned_pms` | `()` | Production-method keys to exclude. Every production configuration containing any listed method is forced to zero levels. |
| `banned_building_groups` | `()` | Building-group keys to exclude. Configurations whose `building_group` exactly matches a listed key are forced to zero; parent-group descendants are not matched automatically. |
| `era_cap` | `None` | Highest permitted technology era. Configurations whose production-table `era` exceeds this value are forced to zero levels. Requires an era-enriched production table. |
| `throughput_multipliers` | `()` | `(building, multiplier)` pairs applied to every configuration of that building. `1.5` means 150% throughput (+50%). Gross goods inputs and outputs both scale; employment and construction cost per level do not. Repeated entries for one building multiply together. |

All optimizers disable level-dependent economy-of-scale bonuses. Use fixed
`throughput_multipliers` to represent throughput assumptions in the scenario.

#### Capacity and relationship constraints

| Attribute | Default | Meaning |
| --- | --- | --- |
| `building_level_caps` | `()` | `(building, maximum_levels)` pairs capping the **sum** of levels across all configurations of that building. A zero limit bans the building. State-region resource helpers produce limits in this form. |
| `construction_cost_cap` | `None` | Maximum total construction points: the sum of building levels multiplied by each configuration's `construction_cost`. |
| `employment_cap` | `None` | Maximum total employed population: the sum of building levels multiplied by per-level employment. |
| `arable_land_cap` | `None` | Maximum total arable-land use. Each level in the model's agricultural, plantation, ranching, or subsistence land-use groups consumes one unit; other configurations consume zero. |
| `min_net_infrastructure_usage` | `None` | Minimum total infrastructure usage minus infrastructure generated by production methods, weighted by building levels. Uses the production-table `infrastructure_usage_per_level` column, which already deducts generation; missing values are treated as zero. This is a lower bound on net usage, so `0.0` requires usage to be at least generation. |
| `urbanization_per_center` | `None` | Urbanization points required per level of `building_urban_center`. Enforces an equality: total building urbanization equals this value multiplied by total urban-center levels. For example, `100.0` ties each center level to 100 urbanization points. |

### Example scenario

```python
from vic3_analysis import NominalOptimizer, Scenario

scenario = Scenario(
    min_goods_output=(("automobiles", 100.0),),
    objective="automation",
    default_min_goods_output=0.0,
    era_cap=5,
    banned_pms=("pm_diesel_engines",),
)
state = NominalOptimizer(economy).solve(scenario)
```

## Problem inspection and solving

Use `optimizer.compile(scenario)` to inspect the resulting compiled problem
before solving it, or `optimizer.solve_problem(problem)` to solve an already
compiled problem. Shared context and constraints are compiled by
`BaseOptimizer`; `Scenario` remains configuration-only.

For endogenous national prices, use `MarketOptimizer`. It supports `gdp` and
`gdp_per_capita`, requires `default_min_goods_output=None`, and treats `goods_trade_flow`
and `pop_needs` as fixed market orders that affect prices rather than goods
balance constraints. Its SLSQP solve is local and requires a bounded scenario.
The model excludes shortages, MAPI and local prices, wealth feedback,
endogenous demand, and economy-of-scale bonuses.

```python
from vic3_analysis import MarketOptimizer, Scenario

scenario = Scenario(
    min_goods_output=(("automobiles", 100.0),),
    objective="gdp_per_capita",
    default_min_goods_output=None,
    goods_trade_flow=(("automobiles", -100.0),),
    employment_cap=1_000_000.0,
)
state = MarketOptimizer(economy).solve(scenario)
```

## Equilibrium optimization

For a runnable example and saved building levels, see the
[million-worker GDP search](../showcase/equilibrium-optimization.md).

`EquilibriumOptimizer` chooses building levels while the existing
[household equilibrium solver](economy.md#solving-equilibrium) determines
wealth, consumption, prices, and finances. It supports `gdp`,
`gdp_per_capita`, and `average_wealth`. Population varies with employment;
an employment cap does not require the optimizer to employ everyone.

```python
from vic3_analysis import EquilibriumOptimizer, Scenario

scenario = Scenario(
    objective="average_wealth",
    default_min_goods_output=None,
    workforce_ratio=0.25,
    building_level_caps=tuple(
        (str(building), 100.0)
        for building in economy.df_production["building"].unique()
    ),
)
optimizer = EquilibriumOptimizer(economy)
problem = optimizer.compile(scenario, max_iterations=1000)
state = optimizer.solve_problem(problem, options={"maxiter": 20_000})
print(state.average_wealth, state.gdp_per_capita(annual=True))
print(optimizer.result.success, optimizer.result.message)
print(optimizer.result.equilibrium_failures)
```

The linear scenario region must be feasible and bounded. Capping every
building is one way to ensure boundedness. All shared constraints, fixed trade,
throughput assumptions, and goods-output minima retain their existing meanings.
Unlike `MarketOptimizer`, this optimizer permits any existing
`default_min_goods_output` setting. `scenario.pop_needs` must be empty,
including when a supplied entry would have amount zero.

`EquilibriumProblem` exposes read-only matrices, named constraint slices, a
nominal GDP `warm_start` LP, `evaluate(levels)` returning a verified state,
and `objective(levels)` returning its negative, unscaled objective value.
Direct evaluation validates physical levels but does not enforce scenario
constraints. `solve()` compiles and solves in one call with the same controls.

Each evaluation rebuilds supply-dependent consumption baskets and starts from
the same `initial_wealth` matrix, defaulting to profession starting tiers. This
prevents evaluation order from selecting different wealth histories. An
explicit seed must match configurations × professions; it is defensively
copied. `max_iterations=1000`, `rtol=1e-9`, and `atol=1e-8` control the inner
equilibrium solver and are frozen in the compiled problem. Empty-population
GDP per capita and average wealth remain zero.

The outer search uses deterministic COBYLA local search without derivatives.
Wealth tiers can cause jumps and plateaus, so search termination does not
certify a global optimum or smooth-objective stationarity. A supplied `x0`
must satisfy the scenario; otherwise the nominal GDP LP supplies a start.
Fixed-zero configurations are removed from search coordinates, and every
returned array still follows the full economy index order. Free coordinates
are scaled by `max(1, abs(starting_level))`. Constraint rows are normalized
by `1 + abs(rhs)`; feasibility is independently checked in original units
with the existing `1e-7 * (1 + abs(rhs))` tolerance.

Solver `options` default to `maxiter=20_000`, `rhobeg=1`, `tol=1e-4`,
`catol=1e-7`, and `disp=0`. `maxiter` is a **hard trial-evaluation budget**,
including initialization and physically rejected trials. An immediately
repeated point reuses the preceding score. Fresh verification of the winner
does not consume this budget. Full vanilla searches can take tens of minutes or longer;
use a smaller budget for exploration. `f_target`, when supplied, uses the
internal minimizing score: `arctan(-metric / scale)`, where `scale` is at least
one and is fixed from the first converged trial's metric magnitude. The bounded
transform preserves metric ordering and gives rejected trials a strictly worse
finite penalty. `problem.objective()` and `result.fun` retain unscaled units.

`EquilibriumError` trial outcomes are rejected and counted by status while
search continues. Invalid model inputs and unexpected calculation errors
propagate. Stationary states with `loss_buildings` or
`unaffordable_floor_cells` remain valid results under the existing accounting
policy; no sustainability constraint, subsidy, or financing model is added.

The optimizer retains the best feasible converged state and independently
reevaluates it before returning. Budget exhaustion returns that state with
`optimizer.result.success == False` and an explicit message. Always inspect
search status separately from `state.equilibrium_diagnostics.status`, which
must be `"converged"` on a returned state. Other ordinary COBYLA termination
statuses also remain visible on the result.

`result.x` and `result.fun` match the returned state. `result.nfev` counts
trial evaluations; `result.equilibrium_evaluations` counts inner attempts;
`result.equilibrium_failures` maps failure statuses to counts; and
`result.last_equilibrium_error` retains the last failed inner snapshot.
`result.solver_result` retains raw COBYLA output, or `None` when COBYLA was
skipped or interrupted by the hard budget. Working memory retains only the
best state, the last failure, and the preceding score. If no feasible converged
state is found, solving raises `ValueError` with these diagnostics still
available on `.result`. A failure during final verification propagates and
marks the retained result unsuccessful.

## State-region limits

```python
from vic3_analysis import (
    StateRegionsParser,
    state_region_arable_land_limit,
    state_region_resource_limits,
)

regions = StateRegionsParser().to_dataframe()
keys = ("STATE_KANTO", "STATE_KANSAI")
limits = state_region_resource_limits(regions, keys)
land = state_region_arable_land_limit(regions, keys)

scenario = Scenario(
    objective="gdp",
    default_min_goods_output=0.0,
    building_level_caps=tuple(limits.items()),
    arable_land_cap=land,
)
```

See the [optimization API](../api/optimization.md)
and [resource-limited optimization showcase](../showcase/resource-limited-optimization.md)
for a complete regional experiment.
