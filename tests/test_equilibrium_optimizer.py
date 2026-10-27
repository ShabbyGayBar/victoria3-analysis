# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Equilibrium optimization acceptance tests with independent accounting checks."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest
import scipy.optimize as opt

from vic3_analysis import (
    BaseOptimizer,
    Economy,
    EconomyState,
    EquilibriumError,
    EquilibriumOptimizer,
    EquilibriumProblem,
    MarketOptimizer,
    NominalOptimizer,
    Scenario,
)
from vic3_analysis.optimize.equilibrium import _metric, _Search


@pytest.fixture(scope="module")
def toy_economy() -> Economy:
    """Two cooperatives with stable second and third wealth tiers."""
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["farm_a", "farm_b"],
                "production_method": ["pm_a", "pm_b"],
                "building_group": ["bg_agriculture", "bg_industry"],
                "era": [1, 2],
                "goods_food": [2.1, 3.1],
                "employment_workers": [10_000.0, 10_000.0],
                "employment": [10_000.0, 10_000.0],
                "construction_cost": [1.0, 2.0],
                "urbanization": [1.0, -1.0],
                "infrastructure_usage_per_level": [1.0, 1.0],
                "economy_of_scale": [True, True],
            }
        ),
        df_goods=pd.DataFrame({"key": ["food"], "cost": [1.0]}),
        df_pop_types=pd.DataFrame(
            {
                "key": ["workers", "unused"],
                "start_quality_of_life": [1, 999],
                "wage_weight": [1.0, 1.0],
                "consumption_mult": [1.0, 1.0],
                "dependent_wage": [0.0, 0.0],
            }
        ),
        df_pop_needs=pd.DataFrame(
            {
                "key": ["popneed_food"],
                "goods": ["food"],
                "weight": [1.0],
                "min_supply_share": [0.0],
                "max_supply_share": [1.0],
                "is_default": [True],
            }
        ),
        df_buy_packages=pd.DataFrame(
            {"wealth": [1, 2, 3], "popneed_food": [1.0, 2.0, 3.0]}
        ),
    )


@pytest.fixture(scope="module")
def vanilla_economy() -> Economy:
    return Economy()


def _scenario(objective: str = "gdp") -> Scenario:
    return Scenario(
        objective=objective,
        building_level_caps=(("farm_a", 1.0), ("farm_b", 1.0)),
        employment_cap=10_000.0,
    )


def _assert_accounting(model: Economy, state: EconomyState) -> None:
    """Recompute demand, prices, finances, and stationarity independently."""
    assert state.equilibrium_diagnostics is not None
    assert state.equilibrium_diagnostics.status == "converged"
    np.testing.assert_allclose(state.pop_buy_orders, model.pop_buy_orders(state))
    np.testing.assert_allclose(
        state.market_prices, model.market_prices(state.buy_orders, state.sell_orders)
    )
    assert state.pop_income is not None
    assert state.pop_expenses is not None
    np.testing.assert_allclose(state.pop_income, model.pop_income(state))
    np.testing.assert_allclose(state.pop_expenses, model.pop_expenses(state))
    market, households = model.iterate(state.context, state.market, state.households)
    assert market is state.market
    assert households is state.households


@pytest.mark.parametrize("objective", ["gdp", "gdp_per_capita", "average_wealth"])
def test_improves_start_and_returns_consistent_results(
    toy_economy: Economy, objective: str
):
    optimizer = EquilibriumOptimizer(toy_economy)
    assert isinstance(optimizer, BaseOptimizer)
    problem = optimizer.compile(_scenario(objective))
    assert isinstance(problem, EquilibriumProblem)
    starting = np.array([0.9, 0.1])
    original = problem.objective(starting)
    state = optimizer.solve_problem(problem, x0=starting, options={"maxiter": 200})
    assert optimizer.problem is problem
    assert optimizer.scenario is problem.scenario
    result = optimizer.result
    assert result is not None
    assert result.success
    assert result.fun < original
    assert result.fun == pytest.approx(problem.objective(state.building_levels))
    np.testing.assert_allclose(result.x, state.building_levels)
    assert state.building_levels[1] > 0.99
    assert state.total_employment <= 10_000.0 * (1 + 1e-7)
    assert state.average_wealth > 2.99
    assert result.nfev <= 200
    assert result.solver_result is not None
    assert result.equilibrium_failures == {}
    np.testing.assert_array_equal(starting, [0.9, 0.1])
    _assert_accounting(toy_economy, state)


def test_immutable_compilation_and_fixed_seed(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    wealth = np.array([[2, 999], [3, 999]])
    problem = optimizer.compile(_scenario(), initial_wealth=wealth, max_iterations=50)
    wealth[:, 0] = 1
    np.testing.assert_array_equal(problem.initial_wealth, [[2, 999], [3, 999]])
    with pytest.raises(FrozenInstanceError):
        setattr(problem, "max_iterations", 10)  # noqa: B010
    for array in (problem.initial_wealth, problem.net_matrix, problem.goods_trade_flow):
        with pytest.raises(ValueError, match="read-only"):
            array.flat[0] = 10
    first = problem.evaluate(np.array([0.9, 0.1]))
    problem.evaluate(np.array([0.1, 0.9]))
    repeated = problem.evaluate(np.array([0.9, 0.1]))
    np.testing.assert_array_equal(first.pop_wealth, repeated.pop_wealth)
    np.testing.assert_array_equal(first.market_prices, repeated.market_prices)
    assert optimizer.result is None
    assert optimizer.goods_matrix is problem.net_matrix


def test_nominal_start_and_compile_invalidate_result(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    state = optimizer.solve(_scenario(), options={"maxiter": 1})
    np.testing.assert_allclose(state.building_levels, [0.0, 1.0])
    assert optimizer.result is not None
    assert not optimizer.result.success
    assert optimizer.result.nfev == 1
    assert "budget" in optimizer.result.message
    assert optimizer.result.solver_result is None
    optimizer.compile(_scenario())
    assert optimizer.result is None


def test_hard_budget_during_initialization_and_best_state(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    state = optimizer.solve(
        _scenario(), x0=np.array([0.8, 0.1]), options={"maxiter": 2}
    )
    result = optimizer.result
    assert result is not None
    assert not result.success
    assert result.nfev == 2
    assert "maxiter=2" in result.message
    assert optimizer.problem is not None
    assert result.fun <= optimizer.problem.objective(np.array([0.8, 0.1]))
    np.testing.assert_array_equal(result.x, state.building_levels)
    _assert_accounting(toy_economy, state)


def test_trade_throughput_and_dependents(toy_economy: Economy):
    scenario = replace(
        _scenario("gdp_per_capita"),
        throughput_multipliers=(("farm_a", 1.5),),
        goods_trade_flow=(("food", 0.25),),
        workforce_ratio=0.25,
    )
    optimizer = EquilibriumOptimizer(toy_economy)
    state = optimizer.solve(scenario, x0=np.array([0.5, 0.5]), options={"maxiter": 25})
    np.testing.assert_allclose(
        state.building_goods_flow,
        state.building_levels[:, None] * optimizer.goods_matrix,
    )
    np.testing.assert_allclose(state.goods_trade_flow, [0.25])
    assert state.total_population == pytest.approx(4 * state.total_employment)
    assert optimizer.result is not None
    assert optimizer.result.fun == pytest.approx(-state.gdp_per_capita())
    _assert_accounting(toy_economy, state)


@pytest.mark.parametrize(
    "changes",
    [
        {"banned_pms": ("pm_b",)},
        {"banned_building_groups": ("bg_industry",)},
        {"era_cap": 1},
        {"building_level_caps": (("farm_a", 1.0), ("farm_b", 0.0))},
    ],
)
def test_reduced_coordinates_preserve_full_indexes(toy_economy: Economy, changes):
    optimizer = EquilibriumOptimizer(toy_economy)
    scenario = replace(_scenario(), **changes)
    state = optimizer.solve(scenario, options={"maxiter": 20})
    assert state.building_levels.shape == (2,)
    assert state.building_levels[1] == 0
    assert state.building_levels[0] == pytest.approx(1)
    assert optimizer.problem is not None
    assert optimizer.problem.bounds[1] == (0.0, 0.0)


def test_all_fixed_empty_economy(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    for objective in ("gdp", "gdp_per_capita", "average_wealth"):
        state = optimizer.solve(
            replace(_scenario(objective), banned_pms=("pm_a", "pm_b")),
            options={"maxiter": 1},
        )
        np.testing.assert_array_equal(state.building_levels, [0.0, 0.0])
        assert state.gdp_per_capita() == state.average_wealth == 0
        assert optimizer.result is not None
        assert optimizer.result.success
        assert optimizer.result.nfev == 1
        assert optimizer.result.solver_result is None
        assert optimizer.result.fun == 0
        _assert_accounting(toy_economy, state)


def test_fixed_zero_start_is_exact_despite_feasibility_tolerance(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    state = optimizer.solve(
        replace(_scenario(), banned_pms=("pm_b",)),
        x0=np.array([0.5, 1e-8]),
        options={"maxiter": 1},
    )
    np.testing.assert_array_equal(state.building_levels, [0.5, 0.0])


def test_shared_constraints_and_nonzero_equality(toy_economy: Economy):
    scenario = replace(
        _scenario(),
        min_goods_output=(("food", 1.0),),
        default_min_goods_output=-1.0,
        construction_cost_cap=1.5,
        arable_land_cap=0.5,
        min_net_infrastructure_usage=1.0,
        urbanization_per_center=100.0,
    )
    optimizer = EquilibriumOptimizer(toy_economy)
    problem = optimizer.compile(scenario)
    nominal = NominalOptimizer(toy_economy).compile(scenario)
    for name in ("A_ub", "b_ub", "A_eq", "b_eq"):
        np.testing.assert_array_equal(getattr(problem, name), getattr(nominal, name))
    state = optimizer.solve_problem(problem, options={"maxiter": 30})
    np.testing.assert_allclose(state.building_levels, [0.5, 0.5], atol=1e-7)
    assert problem.inequality_slices == nominal.inequality_slices
    assert problem.equality_slices == nominal.equality_slices
    _assert_accounting(toy_economy, state)


def test_baskets_refresh_with_changed_supply(toy_economy: Economy):
    production = toy_economy.df_production.copy()
    production["goods_other"] = [0.0, 3.1]
    production["goods_food"] = [2.1, 0.0]
    needs = pd.concat(
        [
            toy_economy.df_pop_needs,
            toy_economy.df_pop_needs.assign(goods="other", is_default=False),
        ],
        ignore_index=True,
    )
    model = replace(
        toy_economy,
        df_production=production,
        df_goods=pd.DataFrame({"key": ["food", "other"], "cost": [1.0, 1.0]}),
        df_pop_needs=needs,
    )
    problem = EquilibriumOptimizer(model).compile(_scenario())
    first = problem.evaluate(np.array([1.0, 0.0]))
    second = problem.evaluate(np.array([0.0, 1.0]))
    assert first.context.goods_buy_packages is not second.context.goods_buy_packages
    np.testing.assert_array_equal(first.pop_buy_orders, [2.0, 0.0])
    np.testing.assert_array_equal(second.pop_buy_orders, [0.0, 3.0])
    _assert_accounting(model, first)
    _assert_accounting(model, second)


def _cycling_model(toy_economy: Economy) -> Economy:
    production = toy_economy.df_production.iloc[:1].copy()
    production["goods_food"] = 0.0
    production["goods_output"] = 2.5
    return replace(
        toy_economy,
        df_production=production,
        df_goods=pd.DataFrame({"key": ["food", "output"], "cost": [1.0, 1.0]}),
    )


@pytest.mark.parametrize(
    ("iterations", "status"), [(1, "max_iterations"), (10, "cycle")]
)
def test_failed_trials_are_counted_and_search_recovers(
    toy_economy: Economy, iterations: int, status: str
):
    model = _cycling_model(toy_economy)
    optimizer = EquilibriumOptimizer(model)
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("farm_a", 2.0),),
        goods_trade_flow=(("food", 1.0), ("output", -2.5)),
    )
    state = optimizer.solve(
        scenario,
        x0=np.ones(1),
        max_iterations=iterations,
        options={"maxiter": 50},
    )
    result = optimizer.result
    assert result is not None
    assert result.equilibrium_failures[status] >= 1
    assert isinstance(result.last_equilibrium_error, EquilibriumError)
    assert state.building_levels[0] != 1.0
    _assert_accounting(model, state)


def test_no_valid_equilibrium_preserves_failure_diagnostics(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(_cycling_model(toy_economy))
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("farm_a", 2.0),),
        goods_trade_flow=(("food", 1.0), ("output", -2.5)),
    )
    with pytest.raises(ValueError, match="No feasible converged") as caught:
        optimizer.solve(scenario, x0=np.ones(1), options={"maxiter": 1})
    assert isinstance(caught.value.__cause__, EquilibriumError)
    assert optimizer.result is not None
    assert not optimizer.result.success
    assert optimizer.result.nfev == 1
    assert optimizer.result.x is None
    assert optimizer.result.equilibrium_failures == {"cycle": 1}


def test_rejected_trials_and_single_entry_cache(toy_economy: Economy):
    problem = EquilibriumOptimizer(toy_economy).compile(_scenario())
    search = _Search(problem, 10)
    penalty = search.trial(np.array([-0.1, 0.0]))
    assert search.equilibrium_evaluations == 0
    assert search.trial(np.array([-0.1, 0.0])) == penalty
    assert search.nfev == 1
    assert search.trial(np.array([1.0, 1.0])) < penalty
    assert search.best is None  # physically valid but exceeds employment cap
    assert search.trial(np.array([1.0, 0.0])) < penalty
    assert search.best is not None
    assert search.nfev == 3


def test_financial_flags_are_accepted(toy_economy: Economy):
    production = toy_economy.df_production.iloc[:1].copy()
    production["goods_food"] = -1.0
    model = replace(toy_economy, df_production=production)
    optimizer = EquilibriumOptimizer(model)
    state = optimizer.solve(
        Scenario(
            objective="gdp",
            default_min_goods_output=None,
            building_level_caps=(("farm_a", 1.0),),
            goods_trade_flow=(("food", 10.0),),
        ),
        x0=np.ones(1),
        options={"maxiter": 1},
    )
    assert state.equilibrium_diagnostics is not None
    assert state.equilibrium_diagnostics.loss_buildings == (0,)
    assert state.equilibrium_diagnostics.unaffordable_floor_cells == ((0, 0),)
    _assert_accounting(model, state)


@pytest.mark.parametrize("objective", ["employment", "automation", "construction_cost"])
def test_rejects_unsupported_objectives(toy_economy: Economy, objective: str):
    with pytest.raises(ValueError, match="requires objective"):
        EquilibriumOptimizer(toy_economy).compile(Scenario(objective=objective))


def test_other_optimizers_reject_wealth(toy_economy: Economy):
    for optimizer in (NominalOptimizer(toy_economy), MarketOptimizer(toy_economy)):
        with pytest.raises(ValueError):
            optimizer.compile(Scenario(objective="average_wealth"))


def test_rejects_exogenous_needs_even_when_zero(toy_economy: Economy):
    with pytest.raises(ValueError, match="pop_needs"):
        EquilibriumOptimizer(toy_economy).compile(
            replace(_scenario(), pop_needs=(("food", 0.0),))
        )


@pytest.mark.parametrize("iterations", [0, -1, True, 1.5])
def test_rejects_invalid_iteration_controls(toy_economy: Economy, iterations):
    with pytest.raises(ValueError, match="max_iterations"):
        EquilibriumOptimizer(toy_economy).compile(
            _scenario(), max_iterations=iterations
        )


@pytest.mark.parametrize("value", [-1, True, np.inf, np.nan])
def test_rejects_invalid_tolerances(toy_economy: Economy, value):
    optimizer = EquilibriumOptimizer(toy_economy)
    with pytest.raises(ValueError, match="rtol"):
        optimizer.compile(_scenario(), rtol=value)
    with pytest.raises(ValueError, match="atol"):
        optimizer.compile(_scenario(), atol=value)


@pytest.mark.parametrize(
    "wealth", [np.ones((1, 2)), np.full((2, 2), 1.5), np.full((2, 2), -1)]
)
def test_rejects_invalid_wealth(toy_economy: Economy, wealth: np.ndarray):
    with pytest.raises(ValueError, match="initial_wealth"):
        EquilibriumOptimizer(toy_economy).compile(_scenario(), initial_wealth=wealth)


@pytest.mark.parametrize(
    "options",
    [
        {"maxiter": 0},
        {"maxiter": True},
        {"maxiter": 1.5},
        {"unknown": 1},
        {"rhobeg": 0},
        {"tol": np.nan},
        {"catol": -1},
        {"tol": True},
        {"disp": 4},
        {"disp": 0.5},
        {"f_target": np.inf},
    ],
)
def test_rejects_invalid_solver_options(toy_economy: Economy, options):
    with pytest.raises(ValueError, match="option"):
        EquilibriumOptimizer(toy_economy).solve(_scenario(), options=options)


@pytest.mark.parametrize(
    "levels", [np.ones(1), np.array([np.nan, 0]), np.array([-1.0, 0])]
)
def test_evaluation_validates_physical_levels(toy_economy: Economy, levels: np.ndarray):
    problem = EquilibriumOptimizer(toy_economy).compile(_scenario())
    with pytest.raises(ValueError, match="levels"):
        problem.evaluate(levels)


@pytest.mark.parametrize(
    "levels",
    [
        np.ones(1),
        np.array([np.nan, 0]),
        np.array([-1.0, 0]),
        np.ones(2),
        np.array([2.0, 0]),
    ],
)
def test_rejects_invalid_or_infeasible_start(toy_economy: Economy, levels: np.ndarray):
    with pytest.raises(ValueError, match="x0"):
        EquilibriumOptimizer(toy_economy).solve(_scenario(), x0=levels)


def test_rejects_infeasible_and_unbounded_regions(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    with pytest.raises(ValueError, match="infeasible"):
        optimizer.solve(replace(_scenario(), min_goods_output=(("food", 100.0),)))
    with pytest.raises(ValueError, match="bounded feasible region"):
        optimizer.solve(Scenario(objective="gdp"))


def test_cross_economy_rejection_preserves_existing_binding(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    own = optimizer.compile(_scenario())
    foreign = EquilibriumOptimizer(replace(toy_economy)).compile(_scenario())
    with pytest.raises(ValueError, match="different Economy"):
        optimizer.solve_problem(foreign)
    assert optimizer.problem is own


def test_invalid_model_inputs_propagate(toy_economy: Economy):
    professions = toy_economy.df_pop_types.drop(columns="wage_weight")
    optimizer = EquilibriumOptimizer(replace(toy_economy, df_pop_types=professions))
    with pytest.raises(ValueError, match="wage_weight"):
        optimizer.solve(_scenario(), x0=np.array([1.0, 0.0]), options={"maxiter": 1})


def test_valid_solver_controls_and_irrelevant_zero_rows(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    scenario = replace(_scenario(), banned_pms=("pm_absent",))
    state = optimizer.solve(
        scenario,
        x0=np.array([0.5, 0.5]),
        options={
            "rhobeg": 0.25,
            "tol": 1e-5,
            "catol": 1e-8,
            "disp": 0,
            "f_target": 0.0,
        },
    )
    assert optimizer.result is not None
    assert optimizer.result.success
    _assert_accounting(toy_economy, state)


def test_large_starting_levels_are_scaled(toy_economy: Economy):
    optimizer = EquilibriumOptimizer(toy_economy)
    scenario = Scenario(
        objective="gdp", building_level_caps=(("farm_a", 500.0), ("farm_b", 500.0))
    )
    initial = np.array([100.0, 50.0])
    problem = optimizer.compile(scenario)
    initial_value = problem.objective(initial)
    state = optimizer.solve_problem(problem, x0=initial, options={"maxiter": 10})
    assert optimizer.result is not None
    assert optimizer.result.fun <= initial_value
    _assert_accounting(toy_economy, state)


@pytest.mark.parametrize(
    "failure", ["different_metric", "infeasible", "equilibrium_error"]
)
def test_final_verification_never_returns_stale_success(
    toy_economy: Economy, failure: str
):
    calls = [0]

    class ChangingEconomy(Economy):
        """Inject a changed final evaluation, after a genuine successful trial."""

        def solve(self, building_levels: np.ndarray, *args, **kwargs) -> EconomyState:
            state = super().solve(building_levels, *args, **kwargs)
            calls[0] += 1
            if calls[0] == 1:
                return state
            if failure == "different_metric":
                return replace(
                    state,
                    market=replace(state.market, market_prices=2 * state.market_prices),
                )
            if failure == "infeasible":
                context = replace(state.context, building_levels=np.full(2, 100.0))
                return replace(
                    state,
                    context=context,
                    market=replace(state.market, context=context),
                )
            diagnostics = state.equilibrium_diagnostics
            assert diagnostics is not None
            raise EquilibriumError(
                "Injected final verification failure",
                replace(
                    state,
                    equilibrium_diagnostics=replace(
                        diagnostics, status="verification_failed"
                    ),
                ),
            )

    model = ChangingEconomy(
        df_production=toy_economy.df_production,
        df_goods=toy_economy.df_goods,
        df_pop_types=toy_economy.df_pop_types,
        df_pop_needs=toy_economy.df_pop_needs,
        df_buy_packages=toy_economy.df_buy_packages,
    )
    optimizer = EquilibriumOptimizer(model)
    with pytest.raises((ValueError, EquilibriumError), match="verification"):
        optimizer.solve(_scenario(), x0=np.array([0.5, 0.5]), options={"maxiter": 1})
    assert optimizer.result is not None
    assert not optimizer.result.success
    assert (
        optimizer.result.message == "Equilibrium optimizer final verification failed."
    )
    assert calls[0] == 2


def test_nonfinite_objective_is_rejected(toy_economy: Economy):
    state = EquilibriumOptimizer(toy_economy).compile(_scenario()).evaluate(np.ones(2))
    invalid = replace(
        state, market=replace(state.market, market_prices=np.array([np.inf]))
    )
    with pytest.raises(ValueError, match="objective must be finite"):
        _metric(invalid, "gdp")


def test_numerical_warm_start_failure_is_reported(toy_economy: Economy, monkeypatch):
    real_linprog = opt.linprog
    calls = [0]

    def failing_warm_start(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            return real_linprog(*args, **kwargs)
        return opt.OptimizeResult(success=False, message="numerical solver failure")

    monkeypatch.setattr(opt, "linprog", failing_warm_start)
    with pytest.raises(ValueError, match="Nominal warm-start failed: numerical"):
        EquilibriumOptimizer(toy_economy).solve(_scenario())
    assert calls[0] == 2


def test_full_vanilla_table_with_hard_budget(vanilla_economy: Economy):
    production = vanilla_economy.df_production
    caps = tuple(
        (str(key), float(count + 1))
        for key, count in production["building"].value_counts().items()
    )
    optimizer = EquilibriumOptimizer(vanilla_economy)
    initial = np.ones(len(vanilla_economy.building_index))
    state = optimizer.solve(
        Scenario(
            objective="gdp", default_min_goods_output=None, building_level_caps=caps
        ),
        x0=initial,
        options={"maxiter": 2},
    )
    assert state.building_levels.shape == initial.shape
    assert state.pop_wealth.shape == (len(initial), len(vanilla_economy.pop_index))
    assert state.market_prices.shape == (len(vanilla_economy.goods_index),)
    assert optimizer.result is not None
    assert optimizer.result.nfev == 2
    assert not optimizer.result.success
    _assert_accounting(vanilla_economy, state)
