# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Chain-coordinate optimization with independent building accounting checks."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

from tests.test_equilibrium_optimizer import (
    _assert_accounting,
    _cycling_model,
    _scenario,
    toy_economy,
)
from vic3_analysis import (
    Economy,
    EconomyState,
    EquilibriumError,
    EquilibriumOptimizer,
    Scenario,
    SupplyChainEquilibriumOptimizer,
    sweep_supply_chains,
)

__all__ = ["toy_economy"]  # Re-export the shared pytest fixture.


def _recipes(model: Economy) -> pd.DataFrame:
    return pd.DataFrame(
        np.array([[1.0, 0.0], [0.5, 2.0]]),
        index=pd.Index(model.building_index, name="config"),
        columns=["mixed", "efficient"],
    )


def test_optimizer_snapshots_recipes_and_adds_shared_buildings(toy_economy: Economy):
    recipes = _recipes(toy_economy)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, recipes)
    expected = recipes.copy(deep=True)
    recipes.iloc[:, :] = 0.0
    np.testing.assert_array_equal(
        optimizer.to_building_levels(np.array([2.0, 3.0])), [2, 7]
    )
    report = optimizer.df_building_levels
    report.iloc[:, :] = -1.0
    report.index = ["changed_a", "changed_b"]
    report.columns = ["changed_c", "changed_d"]
    pd.testing.assert_frame_equal(optimizer.df_building_levels, expected)
    assert optimizer.chain_index == ("mixed", "efficient")
    with pytest.raises(AttributeError):
        setattr(optimizer, "chain_index", ("changed",))  # noqa: B010


def test_dataframe_aligns_rows_and_preserves_chain_order(toy_economy: Economy):
    expected = _recipes(toy_economy).iloc[:, ::-1]
    frame = expected.iloc[::-1].copy(deep=True)
    validated = SupplyChainEquilibriumOptimizer.validate_building_levels(
        frame, building_index=tuple(toy_economy.building_index)
    )
    pd.testing.assert_frame_equal(validated, expected)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, frame)
    assert optimizer.chain_index == ("efficient", "mixed")
    np.testing.assert_array_equal(
        optimizer.to_building_levels(np.array([3, 2])), [2, 7]
    )
    frame.iloc[:, :] = 0.0
    frame.index = ["changed_a", "changed_b"]
    frame.columns = ["changed_c", "changed_d"]
    pd.testing.assert_frame_equal(validated, expected)
    pd.testing.assert_frame_equal(optimizer.df_building_levels, expected)


def test_compiled_problem_snapshots_recipe_coefficients(toy_economy: Economy):
    frame = _recipes(toy_economy)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, frame)
    problem = optimizer.compile(_scenario())
    initial = np.array([0.5, 0.1])
    expected = problem.evaluate(initial)
    coefficients = frame.to_numpy(copy=True)
    snapshot = replace(problem, chain_matrix=coefficients)
    coefficients[:] = 0.0
    frame.iloc[:, :] = 0.0
    np.testing.assert_array_equal(snapshot.chain_matrix, problem.chain_matrix)
    with pytest.raises(ValueError, match="read-only"):
        problem.chain_matrix[0, 0] = 0.0
    with pytest.raises(FrozenInstanceError):
        setattr(problem, "chain_index", ("changed",))  # noqa: B010
    actual = optimizer.solve_problem(problem, x0=initial, options={"maxiter": 1})
    np.testing.assert_array_equal(actual.building_levels, expected.building_levels)
    np.testing.assert_array_equal(actual.market_prices, expected.market_prices)
    assert optimizer.result is not None
    np.testing.assert_array_equal(optimizer.result.x, initial)
    np.testing.assert_array_equal(
        optimizer.result.building_levels, actual.building_levels
    )


def test_dataframe_skips_failed_columns_with_warning(toy_economy: Economy):
    frame = pd.DataFrame(
        {
            "failed_a": [np.nan, np.nan],
            "usable": [1.0, 0.5],
            "failed_b": [np.nan, np.nan],
        },
        index=toy_economy.building_index,
    )
    with pytest.warns(UserWarning, match="failed_a, failed_b"):
        optimizer = SupplyChainEquilibriumOptimizer(toy_economy, frame)
    assert optimizer.chain_index == ("usable",)
    np.testing.assert_array_equal(
        optimizer.df_building_levels.to_numpy(), [[1.0], [0.5]]
    )
    assert frame.columns.tolist() == ["failed_a", "usable", "failed_b"]


def test_dataframe_rejects_all_failed_and_empty_recipes(toy_economy: Economy):
    frame = pd.DataFrame({"failed": [np.nan, np.nan]}, index=toy_economy.building_index)
    with (
        pytest.warns(UserWarning, match="failed"),
        pytest.raises(ValueError, match="No usable"),
    ):
        SupplyChainEquilibriumOptimizer(toy_economy, frame)
    with pytest.raises(ValueError, match="No usable"):
        SupplyChainEquilibriumOptimizer(toy_economy, frame.iloc[:, :0])


@pytest.mark.parametrize(
    "values",
    [[np.nan, 1.0], [np.inf, 1.0], [-1.0, 1.0], [0.0, 0.0], ["bad", 1.0]],
)
def test_dataframe_rejects_invalid_coefficients(toy_economy: Economy, values: list):
    frame = pd.DataFrame({"recipe": values}, index=toy_economy.building_index)
    with pytest.raises(ValueError, match="finite|nonzero|numeric"):
        SupplyChainEquilibriumOptimizer(toy_economy, frame)


@pytest.mark.parametrize("axis", ["index", "columns"])
@pytest.mark.parametrize(
    "labels", [["duplicate", "duplicate"], ["", "b"], [1, "b"], [None, "b"]]
)
def test_dataframe_rejects_invalid_labels(
    toy_economy: Economy, axis: str, labels: list
):
    frame = pd.DataFrame(
        np.ones((2, 2)), index=toy_economy.building_index, columns=["a", "b"]
    )
    setattr(frame, axis, labels)
    with pytest.raises(ValueError, match="labels"):
        SupplyChainEquilibriumOptimizer(toy_economy, frame)


@pytest.mark.parametrize("failure", ["missing", "extra", "unknown"])
def test_dataframe_requires_exact_configuration_set(toy_economy: Economy, failure: str):
    frame = pd.DataFrame({"recipe": [1.0, 0.5]}, index=toy_economy.building_index)
    if failure == "missing":
        frame = frame.iloc[:1]
    elif failure == "extra":
        frame.loc["unknown"] = 0.0
    else:
        frame.index = ["unknown", toy_economy.building_index[1]]
    with pytest.raises(ValueError, match="exactly"):
        SupplyChainEquilibriumOptimizer(toy_economy, frame)


def test_sweep_dataframe_maps_chain_levels_to_equilibrium(toy_economy: Economy):
    sweep = sweep_supply_chains(
        toy_economy, Scenario(objective="construction_cost"), target_value=2.1
    )
    assert not sweep.results
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, sweep.df_building_levels)
    state = optimizer.solve(_scenario(), x0=np.array([0.5]), options={"maxiter": 1})
    assert optimizer.chain_index == ("food",)
    np.testing.assert_allclose(
        state.building_levels, sweep.df_building_levels.to_numpy() @ np.array([0.5])
    )
    _assert_accounting(toy_economy, state)


@pytest.mark.parametrize(
    "levels", [np.ones(1), np.array([-1, 0]), np.array([np.nan, 0])]
)
def test_invalid_vectors(toy_economy: Economy, levels: np.ndarray):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    for transform in (optimizer.to_building_levels, problem.to_building_levels):
        with pytest.raises(ValueError, match="chain_levels"):
            transform(levels)


def test_overflow_is_rejected(toy_economy: Economy):
    frame = pd.DataFrame({"chain": [1e308, 0.0]}, index=toy_economy.building_index)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, frame)
    with pytest.raises(ValueError, match="finite"):
        optimizer.to_building_levels(np.array([1e308]))


def test_alignment_and_problem_validation(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    with pytest.raises(ValueError, match="configurations"):
        replace(problem, chain_matrix=problem.chain_matrix[:1])
    other_model = replace(toy_economy)
    with pytest.raises(ValueError, match="different Economy"):
        replace(
            problem,
            building_problem=EquilibriumOptimizer(other_model).compile(_scenario()),
        )
    with pytest.raises(ValueError, match="bounds"):
        replace(problem, bounds=((0.0, None),))
    with pytest.raises(TypeError, match="Expected"):
        optimizer.solve_problem(problem.building_problem)
    with pytest.raises(ValueError, match="different supply-chain optimizer"):
        SupplyChainEquilibriumOptimizer(
            toy_economy, _recipes(toy_economy)
        ).solve_problem(problem)


@pytest.mark.parametrize("labels", [(), ("", "efficient"), ("mixed", "mixed")])
def test_compiled_problem_rejects_invalid_chain_labels(
    toy_economy: Economy, labels: tuple[str, ...]
):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    with pytest.raises(ValueError, match="labels"):
        replace(problem, chain_index=labels)


@pytest.mark.parametrize(
    "matrix", [np.zeros((2, 2)), np.array([[1, -1], [0, 1]]), np.full((2, 2), np.nan)]
)
def test_compiled_problem_rejects_invalid_coefficients(
    toy_economy: Economy, matrix: np.ndarray
):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    with pytest.raises(ValueError, match="finite|nonzero"):
        replace(problem, chain_matrix=matrix)


@pytest.mark.parametrize("change", ["coefficients", "labels"])
def test_solver_rejects_replaced_recipe_mapping(toy_economy: Economy, change: str):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    altered = (
        replace(problem, chain_matrix=problem.chain_matrix * 2.0)
        if change == "coefficients"
        else replace(problem, chain_index=problem.chain_index[::-1])
    )
    with pytest.raises(ValueError, match="different supply-chain optimizer or recipes"):
        optimizer.solve_problem(altered)


@pytest.mark.parametrize("objective", ["gdp", "gdp_per_capita", "average_wealth"])
def test_mapping_accounting_constraints_and_improvement(
    toy_economy: Economy, objective: str
):
    recipes = _recipes(toy_economy)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, recipes)
    problem = optimizer.compile(_scenario(objective))
    building = problem.building_problem
    assert problem.A_ub is not None and building.A_ub is not None
    np.testing.assert_allclose(problem.A_ub, building.A_ub @ recipes.to_numpy())
    np.testing.assert_allclose(
        problem.warm_start.objective_vector,
        recipes.to_numpy().T @ building.warm_start.objective_vector,
    )
    assert problem.inequality_slices == building.inequality_slices
    initial = np.array([0.5, 0.1])
    expected = building.evaluate(optimizer.to_building_levels(initial))
    actual = problem.evaluate(initial)
    np.testing.assert_array_equal(actual.market_prices, expected.market_prices)
    np.testing.assert_array_equal(actual.pop_wealth, expected.pop_wealth)
    state = optimizer.solve_problem(problem, x0=initial, options={"maxiter": 200})
    result = optimizer.result
    assert result is not None
    assert result.fun < problem.objective(initial)
    assert result.fun == pytest.approx(problem.objective(result.x))
    np.testing.assert_allclose(state.building_levels, recipes.to_numpy() @ result.x)
    np.testing.assert_array_equal(result.building_levels, state.building_levels)
    _assert_accounting(toy_economy, state)


def test_non_square_search_and_budget(toy_economy: Economy):
    recipes = pd.DataFrame({"mixed": [1.0, 0.5]}, index=toy_economy.building_index)
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, recipes)
    state = optimizer.solve(_scenario(), x0=np.array([0.5]), options={"maxiter": 1})
    result = optimizer.result
    assert result is not None and not result.success
    assert result.nfev == 1
    assert result.x.shape == (1,)
    np.testing.assert_array_equal(state.building_levels, [0.5, 0.25])
    np.testing.assert_array_equal(result.building_levels, state.building_levels)


def test_warm_start_and_banned_configuration(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    scenario = replace(_scenario(), banned_building_groups=("bg_agriculture",))
    problem = optimizer.compile(scenario)
    assert problem.bounds[0] == (0.0, 0.0)
    state = optimizer.solve_problem(problem, options={"maxiter": 1})
    assert optimizer.result is not None
    np.testing.assert_allclose(optimizer.result.x, [0, 0.5])
    np.testing.assert_allclose(state.building_levels, [0, 1])


def test_equalities_and_all_fixed_chains(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    scenario = replace(_scenario(), urbanization_per_center=0.5)
    problem = optimizer.compile(scenario)
    assert problem.A_eq is not None and problem.building_problem.A_eq is not None
    np.testing.assert_allclose(
        problem.A_eq, problem.building_problem.A_eq @ problem.chain_matrix
    )
    fixed = replace(_scenario(), building_level_caps=(("farm_a", 0.0), ("farm_b", 0.0)))
    state = optimizer.solve(fixed, options={"maxiter": 1})
    np.testing.assert_array_equal(state.building_levels, [0, 0])
    assert optimizer.result is not None and optimizer.result.success


def test_infeasible_unbounded_and_failed_equilibrium(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    with pytest.raises(ValueError, match="infeasible"):
        optimizer.solve(replace(_scenario(), min_goods_output=(("food", 1000.0),)))
    with pytest.raises(ValueError, match="bounded"):
        optimizer.solve(Scenario(objective="gdp"))
    with pytest.raises(ValueError, match="No feasible converged"):
        optimizer.solve(
            _scenario(),
            x0=np.array([0.5, 0.1]),
            max_iterations=1,
            options={"maxiter": 1},
        )
    assert optimizer.result is not None
    assert optimizer.result.last_equilibrium_error is not None
    assert optimizer.result.building_levels is None


def test_fixed_wealth_seed_and_trade(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    scenario = replace(
        _scenario(),
        goods_import=(("food", 1.0),),
        goods_export=(("food", 0.5),),
        throughput_multipliers=(("farm_a", 1.2),),
    )
    problem = optimizer.compile(scenario, initial_wealth=np.array([[2, 999], [3, 999]]))
    levels = np.array([0.5, 0.1])
    state = problem.evaluate(levels)
    problem.evaluate(np.array([0.1, 0.2]))
    repeated = problem.evaluate(levels)
    np.testing.assert_array_equal(state.market_prices, repeated.market_prices)
    np.testing.assert_array_equal(state.goods_import, [1.0])
    np.testing.assert_array_equal(state.goods_export, [0.5])


def test_final_verification_retains_failure_status(toy_economy: Economy):
    class ChangingEconomy(Economy):
        calls = 0

        def solve(self, building_levels: np.ndarray, *args, **kwargs) -> EconomyState:
            state = super().solve(building_levels, *args, **kwargs)
            self.calls += 1
            if self.calls > 1:
                diagnostics = state.equilibrium_diagnostics
                assert diagnostics is not None
                raise EquilibriumError(
                    "verification failed",
                    replace(
                        state,
                        equilibrium_diagnostics=replace(
                            diagnostics, status="verification_failed"
                        ),
                    ),
                )
            return state

    model = ChangingEconomy(
        df_production=toy_economy.df_production,
        df_goods=toy_economy.df_goods,
        df_pop_types=toy_economy.df_pop_types,
        df_pop_needs=toy_economy.df_pop_needs,
        df_buy_packages=toy_economy.df_buy_packages,
    )
    optimizer = SupplyChainEquilibriumOptimizer(model, _recipes(model))
    with pytest.raises(EquilibriumError, match="verification"):
        optimizer.solve(_scenario(), x0=np.array([0.5, 0.1]), options={"maxiter": 1})
    assert optimizer.result is not None and not optimizer.result.success
    np.testing.assert_array_equal(optimizer.result.building_levels, [0.5, 0.45])


@pytest.mark.parametrize("constrained", [False, True])
def test_finite_building_bounds_are_transformed(
    toy_economy: Economy, monkeypatch: pytest.MonkeyPatch, constrained: bool
):
    scenario = (
        _scenario()
        if constrained
        else Scenario(objective="gdp", default_min_goods_output=None)
    )
    building = EquilibriumOptimizer(toy_economy).compile(scenario)
    building = replace(building, bounds=((0.2, 0.8), (0.0, 0.9)))
    monkeypatch.setattr(
        EquilibriumOptimizer, "compile", lambda *_args, **_kwargs: building
    )
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(scenario)
    assert problem.A_ub is not None and problem.b_ub is not None
    rows = problem.inequality_slices["building_bounds"]
    np.testing.assert_array_equal(problem.A_ub[rows], [[1, 0], [-1, 0], [0.5, 2]])
    np.testing.assert_array_equal(problem.b_ub[rows], [0.8, -0.2, 0.9])
    state = optimizer.solve_problem(problem, options={"maxiter": 1})
    assert 0.2 <= state.building_levels[0] <= 0.8
    assert state.building_levels[1] <= 0.9


def test_original_building_feasibility_is_rechecked(toy_economy: Economy):
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, _recipes(toy_economy))
    problem = optimizer.compile(_scenario())
    altered = replace(
        problem,
        building_problem=replace(
            problem.building_problem, bounds=((0.0, 0.0), (0.0, 0.0))
        ),
    )
    with pytest.raises(ValueError, match="building feasibility"):
        optimizer.solve_problem(
            altered, x0=np.array([0.5, 0.1]), options={"maxiter": 1}
        )
    assert optimizer.result is not None and not optimizer.result.success


@pytest.mark.parametrize("iterations,status", [(1, "max_iterations"), (10, "cycle")])
def test_chain_search_recovers_from_failed_equilibria(
    toy_economy: Economy, iterations: int, status: str
):
    model = _cycling_model(toy_economy)
    recipes = pd.DataFrame({"output": [2.0]}, index=model.building_index)
    optimizer = SupplyChainEquilibriumOptimizer(model, recipes)
    state = optimizer.solve(
        Scenario(
            objective="gdp",
            default_min_goods_output=None,
            building_level_caps=(("farm_a", 2.0),),
            goods_import=(("food", 1.0),),
            goods_export=(("output", 2.5),),
        ),
        x0=np.array([0.5]),
        max_iterations=iterations,
        options={"maxiter": 50},
    )
    result = optimizer.result
    assert result is not None and result.equilibrium_failures[status] >= 1
    np.testing.assert_allclose(state.building_levels, recipes.to_numpy() @ result.x)
    _assert_accounting(model, state)
