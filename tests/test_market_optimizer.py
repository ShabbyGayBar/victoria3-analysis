# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Acceptance tests for the nonlinear market-price optimizer."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import OptimizeResult

from vic3_analysis import (
    BaseOptimizer,
    LinearProblem,
    MarketProblem,
)
from vic3_analysis import (
    MarketOptimizer as ExportedMarketOptimizer,
)
from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.market import MarketOptimizer
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.scenario import Scenario


@pytest.fixture(scope="module")
def toy_economy() -> Economy:
    """Return a one-good economy with a closed-form market-GDP optimum."""
    production = pd.DataFrame(
        {
            "building": ["building_test"],
            "production_method": ["pm_test"],
            "goods_test_good": [1.0],
            "employment": [1.0],
            "employment_test_profession": [1.0],
            "construction_cost": [1.0],
            "economy_of_scale": [True],
        }
    )
    goods = pd.DataFrame({"key": ["test_good"], "cost": [1.0]})
    pop_types = pd.DataFrame(
        {"key": ["test_profession"], "start_quality_of_life": [1.0]}
    )
    return Economy(
        df_production=production,
        df_goods=goods,
        df_pop_types=pop_types,
    )


def test_market_optimizer_is_exported_from_package_root():
    assert ExportedMarketOptimizer is MarketOptimizer
    assert issubclass(MarketOptimizer, BaseOptimizer)


def test_market_optimizer_finds_closed_form_interior_optimum(
    toy_economy: Economy,
):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )

    optimizer = MarketOptimizer(toy_economy)
    state = optimizer.solve(scenario)

    assert isinstance(state, EconomyState)
    assert optimizer.result is not None
    assert optimizer.scenario is scenario
    assert isinstance(optimizer.problem, MarketProblem)
    # With one unit of fixed demand, GDP is x * (1.75 - .75x) for
    # 1 <= x <= 2, whose maximum is x = 7/6.
    np.testing.assert_allclose(state.building_levels, [7.0 / 6.0], atol=2e-5)
    assert state.gdp_weekly == pytest.approx(49.0 / 48.0, abs=2e-5)
    np.testing.assert_allclose(
        state.market_prices,
        toy_economy.market_prices(state.buy_orders, state.sell_orders),
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        state.building_levels,
    )


def test_market_optimizer_honors_fixed_throughput_bonus(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 0.75),),
        throughput_multipliers=(("building_test", 2.0),),
        goods_export=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    np.testing.assert_allclose(state.building_levels, [7.0 / 12.0], atol=2e-5)
    np.testing.assert_allclose(state.building_goods_output, [7.0 / 6.0], atol=4e-5)


def test_market_optimizer_maximizes_gdp_per_capita(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp_per_capita",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    assert 0 < state.building_levels[0] <= 0.5 + 2e-5
    assert state.gdp_per_capita() == pytest.approx(1.75, abs=2e-5)


def test_workforce_ratio_scales_compiled_per_capita_objective(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp_per_capita",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
        employment_cap=1.5,
    )
    optimizer = MarketOptimizer(toy_economy)
    workers = optimizer.compile(scenario)
    households = optimizer.compile(replace(scenario, workforce_ratio=0.25))
    levels = np.array([1.2])
    assert households.objective(levels) == pytest.approx(
        workers.objective(levels) * 0.25
    )
    np.testing.assert_allclose(
        households.jacobian(levels), workers.jacobian(levels) * 0.25
    )
    epsilon = 1e-6
    difference = (
        households.objective(levels + epsilon) - households.objective(levels - epsilon)
    ) / (2 * epsilon)
    np.testing.assert_allclose(households.jacobian(levels), [difference], rtol=1e-5)
    np.testing.assert_array_equal(
        households.warm_start.objective_vector, workers.warm_start.objective_vector
    )
    np.testing.assert_array_equal(households.A_ub, workers.A_ub)
    np.testing.assert_array_equal(households.b_ub, workers.b_ub)
    state = optimizer.solve_problem(households)
    assert state.workforce_ratio == 0.25
    assert state.total_population == state.total_employment * 4
    assert state.gdp_per_capita() == pytest.approx(1.75 * 0.25, abs=2e-5)
    assert -households.objective(state.building_levels) == pytest.approx(
        state.gdp_per_capita()
    )


def test_workforce_ratio_does_not_scale_gdp_objective(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )
    optimizer = MarketOptimizer(toy_economy)
    workers = optimizer.compile(scenario)
    households = optimizer.compile(replace(scenario, workforce_ratio=0.25))
    levels = np.array([1.2])
    assert households.objective(levels) == workers.objective(levels)
    np.testing.assert_array_equal(households.jacobian(levels), workers.jacobian(levels))


def test_market_optimizer_preserves_scenario_constraints(
    toy_economy: Economy,
):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        min_goods_output=(("test_good", 1.0),),
        building_level_caps=(("building_test", 1.25),),
        goods_export=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    assert state.building_levels[0] <= 1.25 + 1e-7
    assert state.building_levels[0] >= 1.0 - 1e-7
    assert state.building_levels[0] == pytest.approx(7.0 / 6.0, abs=2e-5)


@pytest.mark.parametrize("trade", [2.0, -3.0, 0.0])
def test_market_context_is_propagated_by_nominal_optimizer(
    toy_economy: Economy, trade: float
):
    scenario = Scenario(
        objective="construction_cost",
        default_min_goods_output=None,
        goods_import=(("test_good", max(trade, 0)),),
        goods_export=(("test_good", max(-trade, 0) + 4.0),),
    )
    state = NominalOptimizer(toy_economy).solve(scenario)
    np.testing.assert_array_equal(state.goods_import, [max(trade, 0)])
    np.testing.assert_array_equal(state.goods_export, [max(-trade, 0) + 4.0])
    np.testing.assert_array_equal(state.pop_buy_orders, [0.0])
    np.testing.assert_array_equal(
        state.sell_orders, state.building_goods_output + state.goods_import
    )
    np.testing.assert_array_equal(
        state.buy_orders, state.building_goods_input + state.goods_export
    )


@pytest.mark.parametrize("direction", [1.0, 2.0])
def test_market_context_duplicate_goods_are_summed(
    toy_economy: Economy, direction: float
):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_import=(("test_good", direction), ("test_good", 2 * direction)),
        goods_export=(("test_good", 1.0), ("test_good", 2.0)),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    np.testing.assert_array_equal(state.goods_import, [3 * direction])
    np.testing.assert_array_equal(state.imports, [max(3 * direction, 0)])
    np.testing.assert_array_equal(state.exports, [3.0])
    np.testing.assert_array_equal(state.pop_buy_orders, [0.0])


def test_market_prices_and_objective_use_both_gross_trade_orders(toy_economy: Economy):
    optimizer = MarketOptimizer(toy_economy)
    problem = optimizer.compile(
        Scenario(
            objective="gdp",
            default_min_goods_output=None,
            min_goods_output=(("test_good", 100.0),),
            building_level_caps=(("building_test", 100.0),),
            goods_import=(("test_good", 100.0),),
            goods_export=(("test_good", 150.0),),
        )
    )
    state = optimizer.solve_problem(problem)
    np.testing.assert_allclose(state.sell_orders, [200.0])
    np.testing.assert_allclose(state.buy_orders, [150.0])
    np.testing.assert_allclose(state.market_prices, [0.75])
    np.testing.assert_array_equal(state.goods_trade_flow, [-50.0])
    np.testing.assert_array_equal(state.pop_buy_orders, [0.0])
    assert state.gdp() == pytest.approx(75.0)
    assert problem.objective(state.building_levels) == pytest.approx(-state.gdp())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("goods_import", (("not_a_good", 1.0),)),
        ("goods_export", (("not_a_good", 1.0),)),
        ("goods_export", (("test_good", -1.0),)),
        ("goods_import", (("test_good", np.nan),)),
        ("goods_export", (("test_good", np.inf),)),
    ),
)
def test_market_context_rejects_invalid_values(
    toy_economy: Economy, field: str, value: tuple[tuple[str, float], ...]
):
    scenario_kwargs = {
        "objective": "gdp",
        "default_min_goods_output": None,
        field: value,
    }
    with pytest.raises(ValueError):
        MarketOptimizer(toy_economy).solve(Scenario(**scenario_kwargs))


def test_market_optimizer_requires_unbounded_import_policy(toy_economy: Economy):
    with pytest.raises(ValueError, match="default_min_goods_output"):
        MarketOptimizer(toy_economy).solve(
            Scenario(objective="gdp", default_min_goods_output=0.0)
        )


def test_market_optimizer_rejects_non_gdp_objective(toy_economy: Economy):
    with pytest.raises(ValueError, match="gdp"):
        MarketOptimizer(toy_economy).solve(
            Scenario(objective="automation", default_min_goods_output=None)
        )


def test_market_optimizer_rejects_infeasible_and_unbounded_regions(
    toy_economy: Economy,
):
    infeasible = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        min_goods_output=(("test_good", 2.0),),
        building_level_caps=(("building_test", 1.0),),
    )
    with pytest.raises(ValueError, match="infeasible"):
        MarketOptimizer(toy_economy).solve(infeasible)

    with pytest.raises(ValueError, match="bounded"):
        MarketOptimizer(toy_economy).solve(
            Scenario(objective="gdp", default_min_goods_output=None)
        )


@pytest.mark.parametrize("trade", [0.2, -0.3])
def test_market_objective_gradient_matches_finite_difference(
    toy_economy: Economy,
    trade: float,
):
    optimizer = MarketOptimizer(toy_economy)
    base = np.array([1.0])
    inputs = np.array([[0.25]])
    outputs = np.array([[1.0]])
    levels = np.array([1.2])
    value, gradient = optimizer._value_and_gradient(
        toy_economy,
        levels,
        inputs,
        outputs,
        outputs - inputs,
        np.array([max(trade, 0)]),
        np.array([1.0 + max(-trade, 0)]),
        base,
    )
    del value

    epsilon = 1e-6
    plus = optimizer._value_and_gradient(
        toy_economy,
        levels + epsilon,
        inputs,
        outputs,
        outputs - inputs,
        np.array([max(trade, 0)]),
        np.array([1.0 + max(-trade, 0)]),
        base,
    )[0]
    minus = optimizer._value_and_gradient(
        toy_economy,
        levels - epsilon,
        inputs,
        outputs,
        outputs - inputs,
        np.array([max(trade, 0)]),
        np.array([1.0 + max(-trade, 0)]),
        base,
    )[0]
    np.testing.assert_allclose(gradient, [(plus - minus) / (2 * epsilon)], rtol=1e-5)


def test_gdp_per_capita_gradient_matches_finite_difference(
    toy_economy: Economy,
):
    optimizer = MarketOptimizer(toy_economy)
    inputs = np.array([[0.25]])
    outputs = np.array([[1.0]])
    trade = np.array([0.3])
    goods_export = np.array([1.0])
    base_prices = np.array([1.0])
    employment = np.array([2.0])

    def value_and_gradient(levels: np.ndarray) -> tuple[float, np.ndarray]:
        gdp, gdp_gradient = optimizer._value_and_gradient(
            toy_economy,
            levels,
            inputs,
            outputs,
            outputs - inputs,
            trade,
            goods_export,
            base_prices,
        )
        return optimizer._per_capita_value_and_gradient(
            gdp, gdp_gradient, levels, employment
        )

    levels = np.array([1.2])
    _value, gradient = value_and_gradient(levels)
    epsilon = 1e-6
    plus = value_and_gradient(levels + epsilon)[0]
    minus = value_and_gradient(levels - epsilon)[0]

    np.testing.assert_allclose(gradient, [(plus - minus) / (2 * epsilon)], rtol=1e-5)


def test_market_price_derivatives_are_stable_at_kinks():
    base = np.array([1.0, 1.0, 1.0, 1.0])
    buy = np.array([1.0, 2.0, 0.0, 1.0])
    sell = np.array([1.0, 1.0, 0.0, 2.0])

    dp_buy, dp_sell = MarketOptimizer._price_derivatives(base, buy, sell)

    assert np.isfinite(dp_buy).all()
    assert np.isfinite(dp_sell).all()
    # Equal orders choose the smooth interior derivative. Capped, empty, and
    # zero-order branches choose the deterministic zero derivative.
    np.testing.assert_allclose((dp_buy[0], dp_sell[0]), (0.75, -0.75))
    np.testing.assert_allclose(dp_buy[1:], [0.0, 0.0, 0.0])
    np.testing.assert_allclose(dp_sell[1:], [0.0, 0.0, 0.0])


@pytest.mark.parametrize(
    "x0",
    (
        np.array([2.0]),
        np.array([-1.0]),
        np.array([np.nan]),
        np.array([0.5]),
    ),
)
def test_market_optimizer_rejects_invalid_initial_points(
    toy_economy: Economy, x0: np.ndarray
):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        min_goods_output=(("test_good", 1.0),),
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )
    with pytest.raises(ValueError, match="x0|feasib"):
        MarketOptimizer(toy_economy).solve(scenario, x0=x0)


def test_market_optimizer_accepts_feasible_x0_and_options(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(
        scenario,
        x0=np.array([1.1]),
        options={"ftol": 1e-12, "maxiter": 100},
    )

    np.testing.assert_allclose(state.building_levels, [7.0 / 6.0], atol=2e-5)


def test_market_optimizer_rejects_x0_for_fixed_zero_configuration():
    production = pd.DataFrame(
        {
            "building": ["building_allowed", "building_banned"],
            "production_method": ["pm_allowed", "pm_banned"],
            "building_group": ["bg_allowed", "bg_banned"],
            "goods_test_good": [1.0, 1.0],
            "employment": [1.0, 1.0],
            "employment_test_profession": [1.0, 1.0],
            "construction_cost": [1.0, 1.0],
            "economy_of_scale": [False, False],
        }
    )
    economy = Economy(
        df_production=production,
        df_goods=pd.DataFrame({"key": ["test_good"], "cost": [1.0]}),
        df_pop_types=pd.DataFrame(
            {"key": ["test_profession"], "start_quality_of_life": [1.0]}
        ),
    )
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        banned_building_groups=("bg_banned",),
        building_level_caps=(("building_allowed", 1.5),),
        goods_export=(("test_good", 1.0),),
    )

    with pytest.raises(ValueError, match="variable bounds"):
        MarketOptimizer(economy).solve(scenario, x0=np.array([1.0, 0.1]))


def test_market_optimizer_compile_clears_stale_result(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )
    optimizer = MarketOptimizer(toy_economy)
    optimizer.solve(scenario)
    with pytest.raises(ValueError, match="Market optimization failed"):
        optimizer.solve(scenario, x0=np.array([1.0]), options={"maxiter": 1})

    assert optimizer.result is None
    assert optimizer.scenario is scenario
    assert isinstance(optimizer.problem, MarketProblem)


def test_market_compile_and_solve_problem(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )
    optimizer = MarketOptimizer(toy_economy)
    problem = optimizer.compile(scenario)
    assert isinstance(problem, MarketProblem)
    assert isinstance(problem.warm_start, LinearProblem)
    assert optimizer.result is None

    state = optimizer.solve_problem(problem)

    np.testing.assert_allclose(state.building_levels, [7.0 / 6.0], atol=2e-5)
    assert optimizer.problem is problem
    assert optimizer.result is not None


def test_market_solve_problem_rejects_other_economy(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
        goods_export=(("test_good", 1.0),),
    )
    problem = MarketOptimizer(toy_economy).compile(scenario)
    other = Economy(
        df_production=toy_economy.df_production.copy(),
        df_goods=toy_economy.df_goods.copy(),
        df_pop_types=toy_economy.df_pop_types.copy(),
    )
    with pytest.raises(ValueError, match="different Economy"):
        MarketOptimizer(other).solve_problem(problem)


def test_market_solve_problem_applies_remaining_equalities(
    toy_economy: Economy,
):
    optimizer = MarketOptimizer(toy_economy)
    problem = optimizer.compile(
        Scenario(
            objective="gdp",
            default_min_goods_output=None,
            building_level_caps=(("building_test", 1.5),),
            goods_export=(("test_good", 1.0),),
        )
    )
    constrained = replace(
        problem,
        A_eq=np.array([[1.0]]),
        b_eq=np.array([1.0]),
    )

    state = optimizer.solve_problem(constrained, x0=np.array([1.0]))

    np.testing.assert_allclose(state.building_levels, [1.0])


def test_retained_slices_remaps_partially_removed_blocks():
    retained = MarketOptimizer._retained_slices(
        {"removed": slice(None, 1), "kept": slice(1, None)},
        np.array([False, True]),
    )
    assert "removed" not in retained
    assert retained["kept"] == slice(0, 1)


def test_market_preflight_reports_other_solver_failures(
    toy_economy: Economy, monkeypatch: pytest.MonkeyPatch
):
    problem = (
        MarketOptimizer(toy_economy)
        .compile(
            Scenario(
                objective="gdp",
                default_min_goods_output=None,
                building_level_caps=(("building_test", 1.5),),
            )
        )
        .warm_start
    )
    monkeypatch.setattr(
        "vic3_analysis.optimize.market.opt.linprog",
        lambda *args, **kwargs: OptimizeResult(
            success=False, status=4, message="numerical failure"
        ),
    )
    with pytest.raises(ValueError, match="preflight failed"):
        MarketOptimizer._check_feasibility_and_boundedness(problem)


def test_market_reports_warm_start_failure(
    toy_economy: Economy, monkeypatch: pytest.MonkeyPatch
):
    optimizer = MarketOptimizer(toy_economy)
    problem = optimizer.compile(
        Scenario(
            objective="gdp",
            default_min_goods_output=None,
            building_level_caps=(("building_test", 1.5),),
        )
    )
    calls = 0

    def fake_linprog(*args: object, **kwargs: object) -> OptimizeResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return OptimizeResult(success=True)
        return OptimizeResult(success=False, message="warm start failed")

    monkeypatch.setattr("vic3_analysis.optimize.market.opt.linprog", fake_linprog)
    with pytest.raises(ValueError, match="Nominal warm-start failed"):
        optimizer.solve_problem(problem)


def test_market_rejects_misaligned_initial_point(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        building_level_caps=(("building_test", 1.5),),
    )
    with pytest.raises(ValueError, match="1-D vector"):
        MarketOptimizer(toy_economy).solve(scenario, x0=np.zeros((1, 1)))


def test_market_rejects_initial_point_violating_equality():
    with pytest.raises(ValueError, match="equality constraints"):
        MarketOptimizer._validate_initial_point(
            np.array([0.0]),
            None,
            None,
            np.array([[1.0]]),
            np.array([1.0]),
            ((0.0, None),),
            1,
        )


def test_per_capita_terms_at_zero_population():
    value, gradient = MarketOptimizer._per_capita_value_and_gradient(
        2.0,
        np.array([3.0]),
        np.array([0.0]),
        np.array([1.0]),
    )
    assert value == 0.0
    np.testing.assert_array_equal(gradient, [0.0])
