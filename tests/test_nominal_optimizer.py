import numpy as np
import pandas as pd
import pytest

from vic3_analysis import state_region_resource_limits
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
    assert hasattr(solver.result, "ineqlin")


def test_solve_satisfies_produce(economy: Economy, automation_scenario: Scenario):
    state = NominalOptimizer(economy).solve(automation_scenario)
    idx = economy.goods_index().index(TERMINAL_GOOD)
    net = float(
        state.building_levels @ automation_scenario.goods_matrix(economy)[:, idx]
    )
    assert net >= 1.0 - 1e-6


def test_solve_satisfies_import_caps(economy: Economy):
    scenario = Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="construction_cost")
    state = NominalOptimizer(economy).solve(scenario)
    net = state.building_levels @ scenario.goods_matrix(economy)
    assert (net >= -1e-6).all()


def test_solve_state_reflects_throughput_bonuses(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="construction_cost",
        throughput_bonuses=(("building_automotive_industry", 2.0),),
    )
    state = NominalOptimizer(economy).solve(scenario)
    np.testing.assert_allclose(
        state.building_goods_input,
        state.building_levels @ scenario.goods_input_matrix(economy),
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        state.building_levels @ scenario.goods_output_matrix(economy),
    )


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

    coal_mines = (
        economy.df_production["building"] == "building_coal_mine"
    ).to_numpy()
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
    marginals = scenario.import_marginals(economy, solver.result)
    assert marginals is not None
    assert marginals.shape == (len(economy.goods_index()),)


def test_import_marginals_without_import_constraint(economy: Economy):
    scenario = Scenario(import_limit=None, objective="construction_cost")
    solver = NominalOptimizer(economy)
    solver.solve(scenario)
    assert scenario.import_marginals(economy, solver.result) is None
