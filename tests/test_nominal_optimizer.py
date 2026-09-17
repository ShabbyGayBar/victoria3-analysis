import numpy as np
import pandas as pd
import pytest
from scipy.optimize import OptimizeResult

from vic3_analysis import LinearProblem, state_region_resource_limits
from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.scenario import Scenario

TERMINAL_GOOD = "automobiles"


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


@pytest.fixture(scope="module")
def solver(economy: Economy) -> NominalOptimizer:
    return NominalOptimizer(economy)


@pytest.fixture(scope="module")
def automation_scenario() -> Scenario:
    return Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="automation")


def test_init_defaults(solver: NominalOptimizer, economy: Economy):
    assert solver.model is economy
    assert solver.result is None
    assert solver.scenario is None
    assert solver.problem is None


def test_solve_returns_state(
    solver: NominalOptimizer,
    automation_scenario: Scenario,
    economy: Economy,
):
    state = solver.solve(automation_scenario)
    assert isinstance(state, EconomyState)
    assert state.building_levels.shape == (len(economy.building_index()),)
    assert solver.scenario is automation_scenario
    assert solver.result is not None
    assert isinstance(solver.problem, LinearProblem)
    assert hasattr(solver.result, "ineqlin")


def test_solve_satisfies_produce(economy: Economy, automation_scenario: Scenario):
    optimizer = NominalOptimizer(economy)
    state = optimizer.solve(automation_scenario)
    idx = economy.goods_index().index(TERMINAL_GOOD)
    net = float(state.building_levels @ optimizer.goods_matrix[:, idx])
    assert net >= 1.0 - 1e-6


def test_solve_satisfies_import_caps(economy: Economy):
    scenario = Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="construction_cost")
    optimizer = NominalOptimizer(economy)
    state = optimizer.solve(scenario)
    net = state.building_levels @ optimizer.goods_matrix
    assert (net >= -1e-6).all()


def test_solve_state_reflects_throughput_bonuses(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="construction_cost",
        throughput_bonuses=(("building_automotive_industry", 2.0),),
    )
    optimizer = NominalOptimizer(economy)
    state = optimizer.solve(scenario)
    np.testing.assert_allclose(
        state.building_goods_input,
        state.building_levels @ optimizer.goods_input_matrix,
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        state.building_levels @ optimizer.goods_output_matrix,
    )


def test_solve_propagates_fixed_market_context(economy: Economy):
    scenario = Scenario(
        objective="construction_cost",
        import_limit=None,
        imports=(("tools", 2.0),),
        exports=(("coal", 3.0),),
        pop_needs=(("grain", 4.0),),
    )
    state = NominalOptimizer(economy).solve(scenario)
    goods = economy.goods_index()
    assert state.imports[goods.index("tools")] == pytest.approx(2.0)
    assert state.exports[goods.index("coal")] == pytest.approx(3.0)
    assert state.pop_needs[goods.index("grain")] == pytest.approx(4.0)


def test_solve_satisfies_building_limits(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="construction_cost",
        building_limits=(("building_dye_plantation", 0.0),),
    )
    state = NominalOptimizer(economy).solve(scenario)
    mask = (economy.df_production["building"] == "building_dye_plantation").to_numpy()
    assert float(state.building_levels[mask].sum()) == pytest.approx(0.0)


def test_solve_satisfies_state_region_resource_limits(economy: Economy):
    state_regions = pd.DataFrame(
        {"key": ["STATE_TEST"], "resource_building_coal_mine": [1]}
    )
    limits = state_region_resource_limits(state_regions, ["STATE_TEST"])
    scenario = Scenario(
        produce=(("coal", 1.0),),
        objective="construction_cost",
        building_limits=tuple(limits.items()),
    )

    state = NominalOptimizer(economy).solve(scenario)

    coal_mines = (economy.df_production["building"] == "building_coal_mine").to_numpy()
    assert float(state.building_levels[coal_mines].sum()) <= 1.0 + 1e-6


def test_solve_satisfies_arable_land_cap(economy: Economy):
    scenario = Scenario(
        produce=(("grain", 1.0),),
        objective="construction_cost",
        arable_land_cap=1.0,
    )

    state = NominalOptimizer(economy).solve(scenario)

    assert economy.arable_land_consumption(state) <= 1.0 + 1e-6


def test_solve_satisfies_urbanization_center(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="construction_cost",
        urbanization_per_center=100.0,
    )
    state = NominalOptimizer(economy).solve(scenario)
    urbanization = (
        economy.df_production["urbanization"].fillna(0).to_numpy(dtype=np.float64)
    )
    mask = (economy.df_production["building"] == "building_urban_center").to_numpy()
    total_urbanization = float(np.dot(state.building_levels, urbanization))
    urban_center_levels = float(state.building_levels[mask].sum())
    np.testing.assert_allclose(total_urbanization, 100.0 * urban_center_levels)


def test_solve_unbounded_raises(economy: Economy):
    scenario = Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="gdp")
    with pytest.raises(ValueError, match="Optimization failed"):
        NominalOptimizer(economy).solve(scenario)


def test_solve_rejects_gdp_per_capita(economy: Economy):
    scenario = Scenario(objective="gdp_per_capita", import_limit=None)
    with pytest.raises(ValueError, match="MarketOptimizer"):
        NominalOptimizer(economy).solve(scenario)


@pytest.mark.parametrize(
    ("objective", "sign", "vector_name"),
    (
        ("gdp", -1.0, "gdp"),
        ("employment", -1.0, "employment"),
        ("automation", 1.0, "employment"),
        ("construction_cost", 1.0, "construction_cost"),
    ),
)
def test_compile_objective_vectors(
    economy: Economy, objective: str, sign: float, vector_name: str
):
    problem = NominalOptimizer(economy).compile(
        Scenario(objective=objective, import_limit=None)
    )
    if vector_name == "gdp":
        expected = problem.gdp_vector
    elif vector_name == "employment":
        expected = economy.employment_vector()
    else:
        expected = economy.construction_cost_vector()
    np.testing.assert_allclose(problem.objective_vector, sign * expected)


def test_compile_defensively_rejects_unknown_objective(economy: Economy):
    scenario = Scenario()
    object.__setattr__(scenario, "objective", "unknown")
    with pytest.raises(ValueError, match="Unknown objective"):
        NominalOptimizer(economy).compile(scenario)


def test_solve_infeasible_raises(economy: Economy):
    # manowars has no producer configurations; autarky + produce is infeasible.
    scenario = Scenario(produce=(("manowars", 1.0),))
    with pytest.raises(ValueError, match="Optimization failed"):
        NominalOptimizer(economy).solve(scenario)


def test_solve_construction_cost_min_zero_levels(economy: Economy):
    scenario = Scenario(objective="construction_cost")
    state = NominalOptimizer(economy).solve(scenario)
    assert isinstance(state, EconomyState)
    np.testing.assert_allclose(state.building_levels, 0.0)


def test_solve_overwrites_previous_result(economy: Economy):
    solver = NominalOptimizer(economy)
    first = Scenario(produce=((TERMINAL_GOOD, 1.0),))
    solver.solve(first)
    assert solver.scenario is first
    second = Scenario(produce=(("steel", 5.0),))
    solver.solve(second)
    assert solver.scenario is second
    assert solver.result is not None


def test_import_marginals_after_solve(economy: Economy):
    scenario = Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="construction_cost")
    solver = NominalOptimizer(economy)
    solver.solve(scenario)
    marginals = solver.import_marginals()
    assert marginals is not None
    assert marginals.shape == (len(economy.goods_index()),)


def test_import_marginals_without_import_constraint(economy: Economy):
    scenario = Scenario(import_limit=None, objective="construction_cost")
    solver = NominalOptimizer(economy)
    solver.solve(scenario)
    assert solver.import_marginals() is None


def test_import_marginals_requires_successful_result(economy: Economy):
    solver = NominalOptimizer(economy)
    assert solver.import_marginals() is None
    solver.compile(Scenario(objective="construction_cost"))
    assert solver.import_marginals() is None


def test_import_marginals_handles_incomplete_solver_metadata(economy: Economy):
    solver = NominalOptimizer(economy)
    solver.compile(Scenario(objective="construction_cost"))
    solver.result = OptimizeResult()
    assert solver.import_marginals() is None
    solver.result = OptimizeResult(ineqlin=OptimizeResult())
    assert solver.import_marginals() is None
    solver.result = OptimizeResult(ineqlin=OptimizeResult(marginals=np.empty(0)))
    assert solver.import_marginals() is None


def test_compile_and_solve_problem(economy: Economy):
    scenario = Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="construction_cost")
    optimizer = NominalOptimizer(economy)
    problem = optimizer.compile(scenario)
    assert optimizer.problem is problem
    assert optimizer.scenario is scenario
    assert optimizer.result is None
    assert set(problem.linprog_args()) == {"c", "A_ub", "b_ub", "A_eq", "b_eq"}

    state = optimizer.solve_problem(problem)

    assert isinstance(state, EconomyState)
    assert optimizer.problem is problem
    assert optimizer.result is not None


def test_solve_problem_rejects_other_economy(economy: Economy):
    problem = NominalOptimizer(economy).compile(
        Scenario(objective="construction_cost", import_limit=None)
    )
    other = Economy(
        df_production=economy.df_production.copy(),
        df_goods=economy.df_goods.copy(),
        df_pop_types=economy.df_pop_types.copy(),
    )
    with pytest.raises(ValueError, match="different Economy"):
        NominalOptimizer(other).solve_problem(problem)
