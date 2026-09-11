"""Acceptance tests for the nonlinear market-price optimizer."""

import numpy as np
import pandas as pd
import pytest

from vic3_analysis import MarketOptimizer as ExportedMarketOptimizer
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


def test_market_optimizer_finds_closed_form_interior_optimum(
    toy_economy: Economy,
):
    scenario = Scenario(
        objective="gdp",
        import_limit=None,
        building_limits=(("building_test", 1.5),),
        pop_needs=(("test_good", 1.0),),
    )

    optimizer = MarketOptimizer(toy_economy)
    state = optimizer.solve(scenario)

    assert isinstance(state, EconomyState)
    assert optimizer.result is not None
    assert optimizer.scenario is scenario
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
        import_limit=None,
        building_limits=(("building_test", 0.75),),
        throughput_bonuses=(("building_test", 2.0),),
        pop_needs=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    np.testing.assert_allclose(state.building_levels, [7.0 / 12.0], atol=2e-5)
    np.testing.assert_allclose(state.building_goods_output, [7.0 / 6.0], atol=4e-5)


def test_market_optimizer_maximizes_gdp_per_capita(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp_per_capita",
        import_limit=None,
        building_limits=(("building_test", 1.5),),
        pop_needs=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    assert 0 < state.building_levels[0] <= 0.5 + 2e-5
    assert state.gdp_per_capita() == pytest.approx(1.75, abs=2e-5)


def test_market_optimizer_preserves_scenario_constraints(
    toy_economy: Economy,
):
    scenario = Scenario(
        objective="gdp",
        import_limit=None,
        produce=(("test_good", 1.0),),
        building_limits=(("building_test", 1.25),),
        pop_needs=(("test_good", 1.0),),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    assert state.building_levels[0] <= 1.25 + 1e-7
    assert state.building_levels[0] >= 1.0 - 1e-7
    assert state.building_levels[0] == pytest.approx(7.0 / 6.0, abs=2e-5)


def test_market_context_is_propagated_by_nominal_optimizer(
    toy_economy: Economy,
):
    scenario = Scenario(
        objective="construction_cost",
        import_limit=None,
        imports=(("test_good", 2.0),),
        exports=(("test_good", 3.0),),
        pop_needs=(("test_good", 4.0),),
    )

    state = NominalOptimizer(toy_economy).solve(scenario)

    np.testing.assert_array_equal(state.imports, [2.0])
    np.testing.assert_array_equal(state.exports, [3.0])
    np.testing.assert_array_equal(state.pop_needs, [4.0])
    np.testing.assert_array_equal(state.sell_orders, state.building_goods_output + 2.0)
    np.testing.assert_array_equal(state.buy_orders, state.building_goods_input + 7.0)


def test_market_context_duplicate_goods_are_summed(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        import_limit=None,
        building_limits=(("building_test", 1.5),),
        imports=(("test_good", 1.0), ("test_good", 2.0)),
        exports=(("test_good", 3.0), ("test_good", 4.0)),
        pop_needs=(("test_good", 1.0), ("test_good", 2.0)),
    )

    state = MarketOptimizer(toy_economy).solve(scenario)

    np.testing.assert_array_equal(state.imports, [3.0])
    np.testing.assert_array_equal(state.exports, [7.0])
    np.testing.assert_array_equal(state.pop_needs, [3.0])


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("imports", (("not_a_good", 1.0),)),
        ("exports", (("not_a_good", 1.0),)),
        ("pop_needs", (("not_a_good", 1.0),)),
        ("imports", (("test_good", -1.0),)),
        ("exports", (("test_good", np.nan),)),
        ("pop_needs", (("test_good", np.inf),)),
    ),
)
def test_market_context_rejects_invalid_values(
    toy_economy: Economy, field: str, value: tuple[tuple[str, float], ...]
):
    scenario_kwargs = {"objective": "gdp", "import_limit": None, field: value}
    with pytest.raises(ValueError):
        MarketOptimizer(toy_economy).solve(Scenario(**scenario_kwargs))


def test_market_optimizer_requires_unbounded_import_policy(toy_economy: Economy):
    with pytest.raises(ValueError, match="import_limit"):
        MarketOptimizer(toy_economy).solve(Scenario(objective="gdp"))


def test_market_optimizer_rejects_non_gdp_objective(toy_economy: Economy):
    with pytest.raises(ValueError, match="gdp"):
        MarketOptimizer(toy_economy).solve(
            Scenario(objective="automation", import_limit=None)
        )


def test_market_optimizer_rejects_infeasible_and_unbounded_regions(
    toy_economy: Economy,
):
    infeasible = Scenario(
        objective="gdp",
        import_limit=None,
        produce=(("test_good", 2.0),),
        building_limits=(("building_test", 1.0),),
    )
    with pytest.raises(ValueError, match="infeasible"):
        MarketOptimizer(toy_economy).solve(infeasible)

    with pytest.raises(ValueError, match="bounded"):
        MarketOptimizer(toy_economy).solve(
            Scenario(objective="gdp", import_limit=None)
        )


def test_market_objective_gradient_matches_finite_difference(
    toy_economy: Economy,
):
    optimizer = MarketOptimizer(toy_economy)
    base = np.array([1.0])
    inputs = np.array([[0.25]])
    outputs = np.array([[1.0]])
    levels = np.array([1.2])
    value, gradient = optimizer._value_and_gradient(
        levels,
        inputs,
        outputs,
        outputs - inputs,
        np.array([0.2]),
        np.array([0.3]),
        np.array([1.0]),
        base,
    )
    del value

    epsilon = 1e-6
    plus = optimizer._value_and_gradient(
        levels + epsilon,
        inputs,
        outputs,
        outputs - inputs,
        np.array([0.2]),
        np.array([0.3]),
        np.array([1.0]),
        base,
    )[0]
    minus = optimizer._value_and_gradient(
        levels - epsilon,
        inputs,
        outputs,
        outputs - inputs,
        np.array([0.2]),
        np.array([0.3]),
        np.array([1.0]),
        base,
    )[0]
    np.testing.assert_allclose(gradient, [(plus - minus) / (2 * epsilon)], rtol=1e-5)


def test_gdp_per_capita_gradient_matches_finite_difference(
    toy_economy: Economy,
):
    optimizer = MarketOptimizer(toy_economy)
    inputs = np.array([[0.25]])
    outputs = np.array([[1.0]])
    imports = np.array([0.2])
    exports = np.array([0.3])
    pop_needs = np.array([1.0])
    base_prices = np.array([1.0])
    employment = np.array([2.0])

    def value_and_gradient(levels: np.ndarray) -> tuple[float, np.ndarray]:
        gdp, gdp_gradient = optimizer._value_and_gradient(
            levels,
            inputs,
            outputs,
            outputs - inputs,
            imports,
            exports,
            pop_needs,
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
        import_limit=None,
        produce=(("test_good", 1.0),),
        building_limits=(("building_test", 1.5),),
        pop_needs=(("test_good", 1.0),),
    )
    with pytest.raises(ValueError, match="x0|feasib"):
        MarketOptimizer(toy_economy).solve(scenario, x0=x0)


def test_market_optimizer_accepts_feasible_x0_and_options(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        import_limit=None,
        building_limits=(("building_test", 1.5),),
        pop_needs=(("test_good", 1.0),),
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
        import_limit=None,
        banned_building_groups=("bg_banned",),
        building_limits=(("building_allowed", 1.5),),
        pop_needs=(("test_good", 1.0),),
    )

    with pytest.raises(ValueError, match="variable bounds"):
        MarketOptimizer(economy).solve(scenario, x0=np.array([1.0, 0.1]))


def test_market_optimizer_failure_preserves_last_success(toy_economy: Economy):
    scenario = Scenario(
        objective="gdp",
        import_limit=None,
        building_limits=(("building_test", 1.5),),
        pop_needs=(("test_good", 1.0),),
    )
    optimizer = MarketOptimizer(toy_economy)
    optimizer.solve(scenario)
    previous_result = optimizer.result
    previous_scenario = optimizer.scenario

    with pytest.raises(ValueError, match="Market optimization failed"):
        optimizer.solve(scenario, x0=np.array([1.0]), options={"maxiter": 1})

    assert optimizer.result is previous_result
    assert optimizer.scenario is previous_scenario
