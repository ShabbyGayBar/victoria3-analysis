# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import FrozenInstanceError, replace
from typing import cast

import numpy as np
import pandas as pd
import pytest

from vic3_analysis import (
    Economy,
    EconomyContext,
    EconomyState,
    EquilibriumDiagnostics,
    EquilibriumError,
    GoodsBuyPackages,
    MarketState,
    PopState,
)


def _assert_goods_buy_packages_equal(
    actual: GoodsBuyPackages, expected: GoodsBuyPackages
) -> None:
    """Compare immutable basket labels and quantities without DataFrame conversion."""
    np.testing.assert_array_equal(actual.wealth, expected.wealth)
    np.testing.assert_allclose(actual.quantities, expected.quantities)


@pytest.fixture
def coefficient_economy() -> Economy:
    """Small model with ordered flows, missing professions, and nullable metadata."""
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["mine", "factory"],
                "production_method": ["pm_mine", "pm_factory"],
                "building_group": ["bg_mining", "bg_agriculture"],
                "parent_group": ["bg_extraction", None],
                "is_subsistence": pd.Series([False, pd.NA], dtype="boolean"),
                "era": [1, 1],
                "goods_ore": [5.0, -3.0],
                "goods_tools": [-2.0, 4.0],
                "employment": [10.0, 20.0],
                "employment_laborers": [10.0, 20.0],
                "construction_cost": [8.0, 12.0],
                "infrastructure_usage_per_level": [2.0, np.nan],
            }
        ),
        df_goods=pd.DataFrame({"key": ["ore", "tools"], "cost": [10.0, 20.0]}),
        df_pop_types=pd.DataFrame(
            {"key": ["laborers", "engineers"], "start_quality_of_life": [5.0, 10.0]}
        ),
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("building_index", ("mine+pm_mine", "factory+pm_factory")),
        ("goods_index", ("ore", "tools")),
        ("pop_index", ("laborers", "engineers")),
        ("producible_goods", ("ore", "tools")),
    ],
)
def test_cached_indexes_are_ordered_tuples(
    coefficient_economy: Economy, name: str, expected: tuple[str, ...]
):
    index = getattr(coefficient_economy, name)
    assert isinstance(index, tuple)
    assert index == expected
    assert index is getattr(coefficient_economy, name)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("goods_input_matrix_unscaled", [[0.0, 2.0], [3.0, 0.0]]),
        ("goods_output_matrix_unscaled", [[5.0, 0.0], [0.0, 4.0]]),
        ("base_prices", [10.0, 20.0]),
        ("employment_matrix", [[10.0, 0.0], [20.0, 0.0]]),
        ("employment_vector", [10.0, 20.0]),
        ("pop_wealth_init", [5.0, 10.0]),
        ("construction_cost_vector", [8.0, 12.0]),
        ("arable_land_vector", [0.0, 1.0]),
        ("infrastructure_vector", [2.0, 0.0]),
    ],
)
def test_cached_coefficients_are_owned_readonly_arrays(
    coefficient_economy: Economy, name: str, expected: list[float] | list[list[float]]
):
    array = getattr(coefficient_economy, name)
    assert isinstance(array, np.ndarray)
    assert array is getattr(coefficient_economy, name)
    assert array.dtype == (np.int64 if name == "pop_wealth_init" else np.float64)
    assert array.flags.owndata
    assert not array.flags.writeable
    np.testing.assert_array_equal(array, expected)
    with pytest.raises(ValueError, match="read-only"):
        array.flat[0] = 999.0


@pytest.mark.parametrize(
    "name", ["df_production", "df_goods", "df_pop_types", "base_prices"]
)
def test_economy_fields_and_cached_properties_are_frozen(
    coefficient_economy: Economy, name: str
):
    value = getattr(coefficient_economy, name)
    with pytest.raises(FrozenInstanceError):
        setattr(coefficient_economy, name, value)


def test_economy_copies_inputs_before_caching(coefficient_economy: Economy):
    source_production = coefficient_economy.df_production.copy(deep=True)
    source_goods = coefficient_economy.df_goods.copy(deep=True)
    source_pops = coefficient_economy.df_pop_types.copy(deep=True)
    model = Economy(
        df_production=source_production,
        df_goods=source_goods,
        df_pop_types=source_pops,
    )
    source_production.loc[0, "goods_ore"] = 999.0
    source_goods.loc[0, "cost"] = 999.0
    source_pops.loc[0, "start_quality_of_life"] = 999.0
    np.testing.assert_array_equal(
        model.goods_output_matrix_unscaled,
        coefficient_economy.goods_output_matrix_unscaled,
    )
    np.testing.assert_array_equal(model.base_prices, coefficient_economy.base_prices)
    np.testing.assert_array_equal(
        model.pop_wealth_init, coefficient_economy.pop_wealth_init
    )
    for actual, original in (
        (model.df_production, coefficient_economy.df_production),
        (model.df_goods, coefficient_economy.df_goods),
        (model.df_pop_types, coefficient_economy.df_pop_types),
    ):
        pd.testing.assert_frame_equal(actual, original)
    assert model != coefficient_economy
    assert {model: "model", coefficient_economy: "source"}[model] == "model"


@pytest.mark.parametrize("method_name", ["goods_input_matrix", "goods_output_matrix"])
def test_goods_matrix_copies_and_scaling_preserve_cache(
    coefficient_economy: Economy, method_name: str
):
    base = getattr(coefficient_economy, f"{method_name}_unscaled")
    original = base.copy()
    method = getattr(coefficient_economy, method_name)
    for multipliers in (None, np.array([2.0, 3.0]), np.array([0.5, 1.0])):
        result = method(multipliers)
        expected = original if multipliers is None else original * multipliers[:, None]
        np.testing.assert_array_equal(result, expected)
        assert result.flags.writeable
        assert not np.shares_memory(result, base)
        result[:] = 999.0
        np.testing.assert_array_equal(base, original)
        assert base is getattr(coefficient_economy, f"{method_name}_unscaled")


def test_missing_infrastructure_and_land_columns_default_to_zero(
    coefficient_economy: Economy,
):
    model = Economy(
        df_production=coefficient_economy.df_production.drop(
            columns=["infrastructure_usage_per_level", "building_group"]
        ),
        df_goods=coefficient_economy.df_goods,
        df_pop_types=coefficient_economy.df_pop_types,
    )
    np.testing.assert_array_equal(model.infrastructure_vector, [0.0, 0.0])
    assert not model.infrastructure_vector.flags.writeable
    np.testing.assert_array_equal(model.arable_land_vector, [0.0, 0.0])
    assert not model.arable_land_vector.flags.writeable


@pytest.mark.parametrize("output_first", [False, True])
def test_missing_goods_columns_warn_and_cache_zero_flows(
    coefficient_economy: Economy, output_first: bool
):
    with pytest.warns(UserWarning, match="Missing goods input columns.*goods_tools"):
        model = Economy(
            df_production=coefficient_economy.df_production.drop(columns="goods_tools"),
            df_goods=coefficient_economy.df_goods,
            df_pop_types=coefficient_economy.df_pop_types,
        )
    if output_first:
        assert model.goods_output_matrix_unscaled.shape == (2, 2)
    np.testing.assert_array_equal(
        model.goods_input_matrix_unscaled, [[0.0, 0.0], [3.0, 0.0]]
    )
    np.testing.assert_array_equal(
        model.goods_output_matrix_unscaled, [[5.0, 0.0], [0.0, 0.0]]
    )
    assert not np.shares_memory(
        model.goods_input_matrix_unscaled, model.goods_output_matrix_unscaled
    )
    assert model.producible_goods == ("ore",)


def test_normalized_production_metadata_is_cached_without_changing_source(
    coefficient_economy: Economy,
):
    original = coefficient_economy.df_production.copy(deep=True)
    metadata = coefficient_economy._supply_chain_production
    assert metadata is coefficient_economy._supply_chain_production
    assert metadata is not coefficient_economy.df_production
    assert metadata["parent_group"].tolist() == ["bg_extraction", ""]
    assert metadata["land_usage"].tolist() == ["", ""]
    for column in ("is_subsistence", "discoverable_resource", "depletable_resource"):
        assert metadata[column].tolist() == [False, False]
    pd.testing.assert_frame_equal(coefficient_economy.df_production, original)


def _make_state(
    building_goods_flow=None,
    goods_trade_flow=None,
    market_prices=None,
    pops=None,
    pop_wealth=None,
    pop_needs=None,
) -> EconomyState:
    n = 3
    z = np.zeros(n, dtype=np.float64)
    context = EconomyContext(
        building_levels=z,
        building_goods_flow=building_goods_flow
        if building_goods_flow is not None
        else np.zeros((n, n), dtype=np.float64),
        goods_trade_flow=goods_trade_flow if goods_trade_flow is not None else z,
        pops=pops if pops is not None else np.zeros((n, n), dtype=np.float64),
    )
    return EconomyState(
        context=context,
        market=MarketState(
            context=context,
            market_prices=market_prices if market_prices is not None else np.ones(n),
        ),
        households=PopState(
            pop_wealth=pop_wealth if pop_wealth is not None else np.zeros((n, n)),
            pop_needs=pop_needs if pop_needs is not None else z,
        ),
    )


def _state_arrays(state: EconomyState) -> dict[str, np.ndarray]:
    """Collect component arrays for input-preservation assertions."""
    result: dict[str, np.ndarray] = {}
    for name in (
        "building_levels",
        "building_goods_flow",
        "goods_trade_flow",
        "pops",
        "market_prices",
        "pop_wealth",
        "pop_needs",
        "pop_income",
        "pop_expenses",
        "consumption_scales",
    ):
        value = getattr(state, name)
        if isinstance(value, np.ndarray):
            result[name] = value
    if state.goods_buy_packages is not None:
        result["goods_buy_packages.quantities"] = state.goods_buy_packages.quantities
        result["goods_buy_packages.wealth"] = state.goods_buy_packages.wealth
    return result


def _replace_context(state: EconomyState, **changes) -> EconomyState:
    """Replace fixed test inputs and rebind market finances to that context."""
    context = replace(state.context, **changes)
    return replace(
        state, context=context, market=replace(state.market, context=context)
    )


def _replace_field(state: EconomyState, name: str, value: np.ndarray) -> EconomyState:
    """Replace a parametrized input on its owning component."""
    if name == "market_prices":
        return replace(state, market=replace(state.market, market_prices=value))
    if name == "pop_wealth":
        return replace(state, households=replace(state.households, pop_wealth=value))
    return _replace_context(state, **{name: value})


def test_context_derives_trade_directions_and_refreshes_cached_orders():
    source = np.array([5.0, -3.0, 0.0])
    state = _make_state(goods_trade_flow=source)
    source[:] = 999.0
    np.testing.assert_array_equal(state.goods_trade_flow, [5.0, -3.0, 0.0])
    np.testing.assert_array_equal(state.sell_orders, [5.0, 0.0, 0.0])
    np.testing.assert_array_equal(state.buy_orders, [0.0, 3.0, 0.0])
    assert state.imports is state.context.imports
    assert state.exports is state.context.exports
    changed = _replace_context(state, goods_trade_flow=-state.goods_trade_flow)
    np.testing.assert_array_equal(changed.imports, [0.0, 3.0, 0.0])
    np.testing.assert_array_equal(changed.exports, [5.0, 0.0, 0.0])
    np.testing.assert_array_equal(changed.sell_orders, [0.0, 3.0, 0.0])
    np.testing.assert_array_equal(changed.buy_orders, [5.0, 0.0, 0.0])
    assert "goods_trade_flow" in EconomyContext.__dataclass_fields__
    assert "imports" not in EconomyContext.__dataclass_fields__
    assert "exports" not in EconomyContext.__dataclass_fields__
    for array in (state.goods_trade_flow, state.imports, state.exports):
        assert array.dtype == np.float64
        assert not array.flags.writeable


def test_state_defensively_copies_and_freezes_input_arrays():
    source = np.arange(9, dtype=np.float64).reshape(3, 3)
    state = _make_state(building_goods_flow=source)

    source[0, 0] = 999.0

    assert state.building_goods_flow[0, 0] == 0.0
    for name in (
        "building_levels",
        "building_goods_flow",
        "goods_trade_flow",
        "market_prices",
        "pops",
        "pop_wealth",
        "pop_needs",
    ):
        array = getattr(state, name)
        assert array.dtype == (np.int64 if name == "pop_wealth" else np.float64)
        assert array.flags.owndata
        assert not array.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            array.flat[0] = 999.0


@pytest.mark.parametrize(
    "name",
    [
        "building_goods_input",
        "building_goods_output",
        "building_surplus",
        "building_deficit",
        "sell_orders",
        "buy_orders",
        "employment_by_profession",
        "average_wealth_by_profession",
        "total_wealth_by_profession",
        "profession_shares",
    ],
)
def test_state_cached_arrays_are_read_only(name: str):
    state = _make_state()
    array = getattr(state, name)

    assert array is getattr(state, name)
    assert array.flags.owndata
    assert not array.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        array.flat[0] = 999.0


def test_state_goods_flows_preserve_opposing_orders_and_value_added():
    state = _make_state(
        building_goods_flow=np.array([[10, -2, 0], [-8, 3, 0], [0, 0, 0]]),
        market_prices=np.array([2, 4, 1]),
    )
    np.testing.assert_array_equal(state.building_goods_input, [8, 2, 0])
    np.testing.assert_array_equal(state.building_goods_output, [10, 3, 0])
    np.testing.assert_array_equal(state.sell_orders, [10, 3, 0])
    np.testing.assert_array_equal(state.buy_orders, [8, 2, 0])
    np.testing.assert_array_equal(state.building_surplus, [12, -4, 0])
    np.testing.assert_array_equal(state.building_deficit, [0, 4, 0])
    assert state.gdp_weekly == pytest.approx(state.building_surplus.sum())


def test_state_replacement_recalculates_cached_flows_and_finances():
    state = _make_state(
        building_goods_flow=np.array([[10, -2, 0], [-8, 3, 0], [0, 0, 0]]),
        market_prices=np.array([2, 4, 1]),
    )
    original_input = state.building_goods_input
    original_output = state.building_goods_output
    original_surplus = state.building_surplus
    original_deficit = state.building_deficit
    repriced = replace(
        state, market=replace(state.market, market_prices=np.array([1, 10, 1]))
    )
    np.testing.assert_array_equal(repriced.building_surplus, [-10, 22, 0])
    np.testing.assert_array_equal(repriced.building_deficit, [10, 0, 0])
    changed = _replace_context(state, building_goods_flow=-state.building_goods_flow)
    np.testing.assert_array_equal(changed.building_goods_input, original_output)
    np.testing.assert_array_equal(changed.building_goods_output, original_input)
    np.testing.assert_array_equal(changed.building_surplus, -original_surplus)
    np.testing.assert_array_equal(changed.building_deficit, [12, 0, 0])
    np.testing.assert_array_equal(state.building_surplus, [12, -4, 0])
    assert state.building_deficit is original_deficit


@pytest.fixture
def income_economy() -> Economy:
    """Cooperatives with mixed professions, a loss, and no game-data dependency."""
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["factory", "factory", "mine"],
                "production_method": ["pm_one", "pm_two", "pm_mine"],
                "goods_product": [40.0, -10.0, 0.0],
                "goods_material": [-10.0, 5.0, 0.0],
                "employment_laborers": [100.0, 20.0, 10.0],
                "employment_engineers": [50.0, 10.0, 0.0],
                "employment_owners": [10.0, 0.0, 0.0],
                "economy_of_scale": [True, True, False],
            }
        ),
        df_goods=pd.DataFrame({"key": ["product", "material"], "cost": [10.0, 10.0]}),
        df_pop_types=pd.DataFrame(
            {
                "key": ["laborers", "engineers", "owners"],
                "start_quality_of_life": [5, 10, 20],
                "wage_weight": [1.0, 2.0, 0.0],
                "paid_private_wage": [True, False, False],
            }
        ),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
    )


def test_calculate_pop_income_weighted_allocation_and_snapshot(income_economy: Economy):
    state = income_economy.solve(np.ones(3))
    arrays = {
        name: value.copy()
        for name, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    source_pops = income_economy.df_pop_types.copy(deep=True)
    source_production = income_economy.df_production.copy(deep=True)
    result = income_economy.calculate_pop_income(state)
    expected = np.array([[150, 150, 0], [0, 0, 0], [0, 0, 0]])
    np.testing.assert_array_equal(result, expected)
    np.testing.assert_array_equal(result.sum(axis=1), [300, 0, 0])
    np.testing.assert_array_equal(state.building_deficit, [0, 50, 0])
    assert result.shape == state.pops.shape
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    for name, value in arrays.items():
        np.testing.assert_array_equal(_state_arrays(state)[name], value)
        assert not np.shares_memory(result, getattr(state, name))
    pd.testing.assert_frame_equal(income_economy.df_pop_types, source_pops)
    pd.testing.assert_frame_equal(income_economy.df_production, source_production)
    result[:] = 999
    np.testing.assert_array_equal(income_economy.calculate_pop_income(state), expected)


def test_calculate_pop_income_uses_stored_flows_prices_and_separate_configs(
    income_economy: Economy,
):
    base_state = income_economy.solve(np.zeros(3))
    state = _replace_context(
        replace(
            base_state,
            market=replace(base_state.market, market_prices=np.array([20, 10])),
        ),
        building_goods_flow=np.array([[40, -10], [20, -10], [0, 0]]),
        pops=np.array([[100, 50, 0], [20, 10, 0], [0, 0, 0]]),
    )
    # Stored flows are authoritative even with zero building levels.
    np.testing.assert_array_equal(
        income_economy.calculate_pop_income(state),
        [[350, 350, 0], [150, 150, 0], [0, 0, 0]],
    )
    reordered = replace(
        income_economy, df_pop_types=income_economy.df_pop_types.iloc[::-1]
    )
    np.testing.assert_array_equal(
        reordered.calculate_pop_income(
            _replace_context(state, pops=state.pops[:, ::-1])
        ),
        income_economy.calculate_pop_income(state)[:, ::-1],
    )


@pytest.mark.parametrize("zero_weights", [True, False])
def test_calculate_pop_income_no_recipients(
    income_economy: Economy, zero_weights: bool
):
    model = income_economy
    state = model.solve(np.ones(3))
    if zero_weights:
        model = replace(model, df_pop_types=model.df_pop_types.assign(wage_weight=0))
    else:
        state = _replace_context(state, pops=np.zeros_like(state.pops))
    with pytest.raises(
        ValueError, match="no positive recipient weight.*factory\\+pm_one"
    ):
        model.calculate_pop_income(state)
    state = _replace_context(
        state, building_goods_flow=np.array([[-1, 0], [0, 0], [0, 0]])
    )
    np.testing.assert_array_equal(model.calculate_pop_income(state), np.zeros((3, 3)))


@pytest.mark.parametrize("method", ["nominal", "market"])
def test_realized_flows_include_levels_throughput_and_scale(
    income_economy: Economy, method: str
):
    levels = np.array([0.5, 1.5, 0])
    state = income_economy.solve(
        levels,
        method=method,
        throughput_multipliers=np.array([1.5, 2.0, 1.0]),
        economy_of_scale_level_cap=1.0,
    )
    expected_flow = (
        np.array([[40, -10], [-10, 5], [0, 0]])
        * np.array([0.5 * 1.51, 1.5 * 2.01, 0])[:, None]
    )
    np.testing.assert_allclose(state.building_goods_flow, expected_flow)
    np.testing.assert_allclose(
        state.pops, levels[:, None] * income_economy.employment_matrix
    )
    np.testing.assert_allclose(
        income_economy.calculate_pop_income(state).sum(axis=1),
        np.maximum(expected_flow @ state.market_prices, 0),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("building_goods_flow", np.zeros(2)),
        ("building_goods_flow", np.zeros((2, 2))),
        ("building_goods_flow", np.zeros((3, 3))),
        ("building_goods_flow", np.full((3, 2), np.nan)),
        ("building_goods_flow", np.full((3, 2), np.inf)),
        ("market_prices", np.zeros(1)),
        ("market_prices", np.zeros((1, 2))),
        ("market_prices", np.array([-1, 10])),
        ("market_prices", np.array([np.nan, 10])),
        ("market_prices", np.array([np.inf, 10])),
        ("pops", np.zeros((3, 2))),
        ("pops", np.full((3, 3), -1)),
        ("pops", np.full((3, 3), np.nan)),
        ("pops", np.full((3, 3), np.inf)),
    ],
)
def test_calculate_pop_income_rejects_invalid_state(
    income_economy: Economy, field: str, value: np.ndarray
):
    state = _replace_field(income_economy.solve(np.ones(3)), field, value)
    with pytest.raises(ValueError, match=field):
        income_economy.calculate_pop_income(state)


@pytest.mark.parametrize("value", [-1, np.nan, np.inf, "invalid"])
def test_calculate_pop_income_rejects_invalid_weights(
    income_economy: Economy, value: float | str
):
    model = replace(
        income_economy,
        df_pop_types=income_economy.df_pop_types.assign(wage_weight=[1, value, 0]),
    )
    with pytest.raises(ValueError, match="wage_weight"):
        model.calculate_pop_income(income_economy.solve(np.ones(3)))


@pytest.mark.parametrize(
    "keys", [["laborers", "laborers", "owners"], ["", "engineers", "owners"]]
)
def test_calculate_pop_income_rejects_invalid_profession_keys(
    income_economy: Economy, keys: list[str]
):
    model = replace(
        income_economy, df_pop_types=income_economy.df_pop_types.assign(key=keys)
    )
    with pytest.raises(ValueError, match="pop_index.*unique non-empty"):
        model.calculate_pop_income(income_economy.solve(np.ones(3)))


def test_calculate_pop_income_requires_wage_weights(income_economy: Economy):
    model = replace(
        income_economy,
        df_pop_types=income_economy.df_pop_types.drop(columns="wage_weight"),
    )
    with pytest.raises(ValueError, match="df_pop_types.*wage_weight"):
        model.calculate_pop_income(income_economy.solve(np.ones(3)))


@pytest.mark.parametrize("case", ["weighted_population", "total_weight", "surplus"])
def test_calculate_pop_income_rejects_overflow(income_economy: Economy, case: str):
    model = income_economy
    state = model.solve(np.ones(3))
    if case == "weighted_population":
        state = _replace_context(state, pops=np.full((3, 3), 1e308))
    elif case == "total_weight":
        model = replace(model, df_pop_types=model.df_pop_types.assign(wage_weight=1))
        state = _replace_context(state, pops=np.full((3, 3), 1e308))
    else:
        state = replace(
            state, market=replace(state.market, market_prices=np.full(2, 1e308))
        )
    with pytest.raises(ValueError, match="finite"):
        model.calculate_pop_income(state)


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


def _first_producing_levels(economy: Economy) -> np.ndarray:
    out = economy.goods_output_matrix()
    idx = int(np.argmax(out.sum(axis=1) > 0))
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    levels[idx] = 1.0
    return levels


def test_sell_orders():
    state = _make_state(
        building_goods_flow=np.array([[10.0, 0.0, 5.0], [0, 0, 0], [0, 0, 0]]),
        goods_trade_flow=np.array([2.0, 1.0, 0.0]),
    )
    np.testing.assert_array_equal(state.sell_orders, np.array([12.0, 1.0, 5.0]))


def test_buy_orders():
    state = _make_state(
        building_goods_flow=np.array([[-3.0, 0.0, -1.0], [0, 0, 0], [0, 0, 0]]),
        goods_trade_flow=np.array([0.0, -2.0, -1.0]),
        pop_needs=np.array([1.0, 1.0, 1.0]),
    )
    np.testing.assert_array_equal(state.buy_orders, np.array([4.0, 3.0, 3.0]))


def test_gdp_weekly():
    state = _make_state(
        building_goods_flow=np.array([[-1, -2, -1], [5, 0, 3], [0, 0, 0]]),
        market_prices=np.array([2.0, 1.0, 4.0]),
    )
    # net = [4, -2, 2]; net * prices = [8, -2, 8]; sum = 14
    assert state.gdp_weekly == pytest.approx(14.0)


def test_gdp_weekly_and_annual():
    state = _make_state(
        building_goods_flow=np.array([[-1, -2, -1], [5, 0, 3], [0, 0, 0]]),
        market_prices=np.array([2.0, 1.0, 4.0]),
    )
    assert state.gdp() == pytest.approx(14.0)
    assert state.gdp(annual=False) == pytest.approx(14.0)
    assert state.gdp(annual=True) == pytest.approx(14.0 * 52)


def test_average_wealth():
    state = _make_state(
        pops=np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]]),
        pop_wealth=np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]]),
    )
    # pops column sums = [10, 30, 0]
    # element-wise: [[80, 400, 0], [120, 800, 0]] -> sum 1400 / employment 40 = 35
    assert state.average_wealth == pytest.approx(35.0)


def test_average_wealth_zero_employment():
    state = _make_state(
        pops=np.zeros((3, 3), dtype=np.float64),
        pop_wealth=np.zeros((3, 3), dtype=np.float64),
    )
    assert state.average_wealth == 0.0


def test_init_loads_tables(economy):
    assert not economy.df_production.empty
    assert not economy.df_goods.empty
    assert not economy.df_pop_types.empty


def test_init_with_explicit_dataframes(economy):
    eco2 = Economy(
        df_production=economy.df_production,
        df_goods=economy.df_goods,
        df_pop_types=economy.df_pop_types,
    )
    for name in ("df_production", "df_goods", "df_pop_types"):
        actual = getattr(eco2, name)
        original = getattr(economy, name)
        assert actual is not original
        pd.testing.assert_frame_equal(actual, original)


def test_explicit_dataframes_are_authoritative_with_language(economy):
    eco2 = Economy(
        df_production=economy.df_production,
        df_goods=economy.df_goods,
        df_pop_types=economy.df_pop_types,
        language="english",
    )
    for name in ("df_production", "df_goods", "df_pop_types"):
        actual = getattr(eco2, name)
        original = getattr(economy, name)
        assert actual is not original
        pd.testing.assert_frame_equal(actual, original)


def test_language_localizes_internally_parsed_tables():
    localized = Economy(language="english")
    assert "building_localization" in localized.df_production.columns
    assert "production_method_localization" in localized.df_production.columns
    assert "building_group_localization" in localized.df_production.columns
    assert "unlocking_tech_localization" in localized.df_production.columns
    assert "key_localization" in localized.df_goods.columns
    assert "key_localization" in localized.df_pop_types.columns


def test_indices_consistent(economy):
    buildings = economy.building_index
    goods_idx = economy.goods_index
    pops = economy.pop_index
    assert len(buildings) == len(economy.df_production)
    assert len(goods_idx) == len(economy.df_goods)
    assert len(pops) == len(economy.df_pop_types)
    assert all("+" in b for b in buildings)
    assert goods_idx == tuple(economy.df_goods["key"].tolist())
    assert pops == tuple(economy.df_pop_types["key"].tolist())


def test_base_prices(economy):
    prices = economy.base_prices
    assert prices.shape == (len(economy.df_goods),)
    assert prices.dtype == np.float64
    np.testing.assert_array_equal(
        prices, economy.df_goods["cost"].to_numpy(dtype=np.float64)
    )


def test_market_prices_balanced_and_empty(economy: Economy):
    n_goods = len(economy.goods_index)
    base_prices = economy.base_prices
    zeros = np.zeros(n_goods, dtype=np.float64)
    balanced = np.full(n_goods, 10.0, dtype=np.float64)

    np.testing.assert_array_equal(economy.market_prices(zeros, zeros), base_prices)
    np.testing.assert_array_equal(
        economy.market_prices(balanced, balanced), base_prices
    )


def test_market_prices_documented_wood_example(economy: Economy):
    wood = economy.goods_index.index("wood")
    buy_orders = np.zeros(len(economy.goods_index), dtype=np.float64)
    sell_orders = np.zeros(len(economy.goods_index), dtype=np.float64)
    buy_orders[wood] = 100.0
    sell_orders[wood] = 120.0

    prices = economy.market_prices(buy_orders, sell_orders)

    assert prices[wood] == pytest.approx(economy.base_prices[wood] * 0.85)
    assert prices[wood] == pytest.approx(17.0)


@pytest.mark.parametrize(
    ("buy_orders", "sell_orders", "factor"),
    [
        (2.0, 0.0, 1.75),
        (0.0, 2.0, 0.25),
        (10.0, 1.0, 1.75),
        (1.0, 10.0, 0.25),
    ],
)
def test_market_prices_caps_and_clamping(
    economy: Economy, buy_orders: float, sell_orders: float, factor: float
):
    good = 0
    buy_vector = np.zeros(len(economy.goods_index), dtype=np.float64)
    sell_vector = np.zeros(len(economy.goods_index), dtype=np.float64)
    buy_vector[good] = buy_orders
    sell_vector[good] = sell_orders

    prices = economy.market_prices(buy_vector, sell_vector)

    assert prices[good] == pytest.approx(economy.base_prices[good] * factor)


@pytest.mark.parametrize("invalid_argument", ["buy_orders", "sell_orders"])
@pytest.mark.parametrize(
    "invalid_kind",
    ["non_1d", "wrong_length", "negative", "nan", "inf"],
)
def test_market_prices_rejects_invalid_orders(
    economy: Economy, invalid_argument: str, invalid_kind: str
):
    n_goods = len(economy.goods_index)
    valid = np.zeros(n_goods, dtype=np.float64)
    if invalid_kind == "non_1d":
        invalid_value = np.zeros((n_goods, 1), dtype=np.float64)
    elif invalid_kind == "wrong_length":
        invalid_value = np.zeros(n_goods + 1, dtype=np.float64)
    elif invalid_kind == "negative":
        invalid_value = valid.copy()
        invalid_value[0] = -1.0
    elif invalid_kind == "nan":
        invalid_value = valid.copy()
        invalid_value[0] = np.nan
    else:
        invalid_value = valid.copy()
        invalid_value[0] = np.inf
    kwargs = {"buy_orders": valid, "sell_orders": valid}
    kwargs[invalid_argument] = cast(
        np.ndarray[tuple[int], np.dtype[np.float64]], invalid_value
    )

    with pytest.raises(ValueError):
        economy.market_prices(**kwargs)


def test_goods_input_matrix(economy):
    mat = np.asarray(economy.goods_input_matrix())
    assert mat.shape == (len(economy.df_production), len(economy.df_goods))
    assert mat.dtype == np.float64
    assert (mat >= 0).all()


def test_goods_output_matrix(economy):
    mat = np.asarray(economy.goods_output_matrix())
    assert mat.shape == (len(economy.df_production), len(economy.df_goods))
    assert mat.dtype == np.float64
    assert (mat >= 0).all()


def test_goods_matrices_with_throughput_multipliers(economy):
    multipliers = np.full(len(economy.building_index), 2.0, dtype=np.float64)
    np.testing.assert_allclose(
        economy.goods_input_matrix(multipliers),
        economy.goods_input_matrix() * multipliers[:, None],
    )
    np.testing.assert_allclose(
        economy.goods_output_matrix(multipliers),
        economy.goods_output_matrix() * multipliers[:, None],
    )


@pytest.mark.parametrize("matrix_method", ["goods_input_matrix", "goods_output_matrix"])
def test_goods_matrices_reject_misaligned_throughput_multipliers(
    economy, matrix_method
):
    method = getattr(economy, matrix_method)
    with pytest.raises(ValueError, match="throughput_multipliers must be a 1-D"):
        method(np.ones((len(economy.building_index), 1), dtype=np.float64))
    with pytest.raises(ValueError, match="throughput_multipliers length"):
        method(np.ones(len(economy.building_index) + 1, dtype=np.float64))


def test_employment_matrix(economy):
    mat = economy.employment_matrix
    assert mat.shape == (len(economy.df_production), len(economy.df_pop_types))
    assert mat.dtype == np.float64


def test_pop_wealth_init(economy):
    w = economy.pop_wealth_init
    assert w.shape == (len(economy.df_pop_types),)
    assert w.dtype == np.int64
    np.testing.assert_array_equal(
        w, economy.df_pop_types["start_quality_of_life"].to_numpy(dtype=np.float64)
    )


@pytest.fixture
def needs_economy() -> Economy:
    """Small complete model with reversed wealth rows and a non-consumed good."""
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["factory", "farm"],
                "production_method": ["pm_factory", "pm_farm"],
                "goods_unused": [0.0, 0.0],
                "goods_a": [100.0, 0.0],
                "goods_b": [100.0, 0.0],
                "employment_workers": [10_000.0, 0.0],
                "employment_peasants": [0.0, 10_000.0],
            }
        ),
        df_goods=pd.DataFrame(
            {"key": ["unused", "a", "b"], "cost": [10.0, 20.0, 40.0]}
        ),
        df_pop_types=pd.DataFrame(
            {
                "key": ["workers", "peasants"],
                "start_quality_of_life": [1, 2],
                "consumption_mult": [np.nan, 0.05],
            }
        ),
        df_pop_needs=pd.DataFrame(
            {
                "key": ["popneed_food", "popneed_food"],
                "goods": ["a", "b"],
                "weight": [1.0, 1.0],
                "min_supply_share": [0.0, 0.0],
                "max_supply_share": [1.0, 1.0],
                "is_default": [True, False],
            }
        ),
        df_buy_packages=pd.DataFrame(
            {
                "wealth": [2, 1],
                "popneed_food": [400.0, 200.0],
                "total_popneeds": [400.0, 200.0],
            }
        ),
    )


@pytest.fixture
def consumption_state(needs_economy: Economy) -> EconomyState:
    """Mixed households at two tiers, with market prices unlike base prices."""
    base_state = needs_economy.solve(np.array([1.0, 1.0]))
    return _replace_context(
        replace(
            base_state,
            market=replace(
                base_state.market, market_prices=np.array([10.0, 40.0, 20.0])
            ),
            households=replace(
                base_state.households, pop_wealth=np.array([[1, 2], [2, 1]])
            ),
        ),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
    )


@pytest.mark.parametrize("workforce_ratio", [1.0, 0.25])
def test_pop_consumption_scales_values_and_ownership(
    needs_economy: Economy, consumption_state: EconomyState, workforce_ratio: float
):
    state = _replace_context(consumption_state, workforce_ratio=workforce_ratio)
    original = {
        key: value.copy()
        for key, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    result = needs_economy.calculate_pop_consumption_scales(state)
    expected = np.array([[0.5, 0.01], [0.3, 0.02]])
    if workforce_ratio == 0.25:
        expected *= 2.5
    np.testing.assert_allclose(result, expected)
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    for key, value in original.items():
        np.testing.assert_array_equal(_state_arrays(state)[key], value)
    assert not np.shares_memory(result, state.pops)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_consumption_scales(state), expected
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_consumption_scales(
            _replace_context(state, pops=2 * state.pops)
        ),
        2 * expected,
    )


def test_pop_consumption_scales_defaults_and_independence(
    needs_economy: Economy, consumption_state: EconomyState
):
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.drop(columns="consumption_mult"),
    )
    expected = np.array([[0.5, 0.2], [0.3, 0.4]])
    changed = _replace_context(
        replace(
            consumption_state,
            market=replace(consumption_state.market, market_prices=np.full(3, np.nan)),
            households=replace(
                consumption_state.households,
                pop_wealth=np.full((2, 2), 999),
                pop_needs=np.full(3, np.nan),
            ),
        ),
        building_goods_flow=np.full((2, 3), np.nan),
        goods_trade_flow=np.full(3, np.nan),
    )
    np.testing.assert_allclose(
        model.calculate_pop_consumption_scales(changed), expected
    )


@pytest.mark.parametrize("supply_packages", [False, True])
@pytest.mark.parametrize("supply_scales", [False, True])
@pytest.mark.parametrize("workforce_ratio", [1.0, 0.25])
def test_pop_expenses_reuse_and_accounting_identity(
    needs_economy: Economy,
    consumption_state: EconomyState,
    supply_packages: bool,
    supply_scales: bool,
    workforce_ratio: float,
):
    state = _replace_context(consumption_state, workforce_ratio=workforce_ratio)
    packages = (
        needs_economy.calculate_goods_buy_packages(state) if supply_packages else None
    )
    scales = (
        needs_economy.calculate_pop_consumption_scales(state) if supply_scales else None
    )
    expenses = needs_economy.calculate_pop_expenses(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    needs = needs_economy.calculate_pop_needs(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    factor = 2.5 if workforce_ratio == 0.25 else 1.0
    np.testing.assert_allclose(
        expenses, np.array([[125.0, 5.0], [150.0, 5.0]]) * factor
    )
    np.testing.assert_allclose(needs, np.array([0.0, 5.7, 2.85]) * factor)
    assert expenses.sum() == pytest.approx(needs @ state.market_prices)
    assert expenses.dtype == np.float64
    assert expenses.flags.owndata and expenses.flags.writeable


def test_pop_expenses_snapshot_and_reordered_baskets(
    needs_economy: Economy, consumption_state: EconomyState
):
    state = consumption_state
    calculated = needs_economy.calculate_goods_buy_packages(state)
    packages = GoodsBuyPackages(calculated.wealth[::-1], calculated.quantities[::-1])
    scales = needs_economy.calculate_pop_consumption_scales(state)
    source_packages = GoodsBuyPackages(packages.wealth, packages.quantities)
    source_scales = scales.copy()
    source_tables = [
        frame.copy(deep=True)
        for frame in (
            needs_economy.df_pop_types,
            needs_economy.df_pop_needs,
            needs_economy.df_buy_packages,
        )
    ]
    source_arrays = {
        key: value.copy()
        for key, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    result = needs_economy.calculate_pop_expenses(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    np.testing.assert_allclose(result, [[125, 5], [150, 5]])
    for key, value in source_arrays.items():
        np.testing.assert_array_equal(_state_arrays(state)[key], value)
        assert not np.shares_memory(result, _state_arrays(state)[key])
    for frame, original in zip(
        (
            needs_economy.df_pop_types,
            needs_economy.df_pop_needs,
            needs_economy.df_buy_packages,
        ),
        source_tables,
    ):
        pd.testing.assert_frame_equal(frame, original)
    np.testing.assert_array_equal(scales, source_scales)
    _assert_goods_buy_packages_equal(packages, source_packages)
    assert not np.shares_memory(result, scales)
    assert not np.shares_memory(result, packages.quantities)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_expenses(
            state, goods_buy_packages=packages, consumption_scales=scales
        ),
        [[125, 5], [150, 5]],
    )


def test_pop_consumption_reuse_after_wealth_and_price_changes(
    needs_economy: Economy, consumption_state: EconomyState
):
    packages = needs_economy.calculate_goods_buy_packages(consumption_state)
    scales = needs_economy.calculate_pop_consumption_scales(consumption_state)
    changed = replace(
        consumption_state,
        households=replace(consumption_state.households, pop_wealth=np.full((2, 2), 2)),
    )
    expected = scales * 500
    np.testing.assert_allclose(
        needs_economy.calculate_pop_expenses(
            changed, goods_buy_packages=packages, consumption_scales=scales
        ),
        expected,
    )
    zero_prices = replace(
        changed, market=replace(changed.market, market_prices=np.zeros(3))
    )
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_expenses(
            zero_prices, goods_buy_packages=packages, consumption_scales=scales
        ),
        np.zeros((2, 2)),
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(changed, consumption_scales=scales),
        needs_economy.calculate_pop_needs(zero_prices, consumption_scales=scales),
    )


@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
@pytest.mark.parametrize("supply_packages", [False, True])
def test_pop_consumption_supplied_scales_are_authoritative(
    needs_economy: Economy,
    consumption_state: EconomyState,
    method: str,
    supply_packages: bool,
):
    state = _replace_context(consumption_state, workforce_ratio=0.25)
    scales = np.array([[1.0, 2.0], [3.0, 4.0]])
    original = scales.copy()
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.assign(consumption_mult=[np.nan, -1]),
    )
    packages = (
        needs_economy.calculate_goods_buy_packages(state) if supply_packages else None
    )
    result = getattr(model, method)(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    expected = (
        [0, 75, 37.5]
        if method == "calculate_pop_needs"
        else [[250, 1000], [1500, 1000]]
    )
    np.testing.assert_allclose(result, expected)
    np.testing.assert_array_equal(scales, original)


@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
@pytest.mark.parametrize("case", ["shape", "negative", "nan", "inf", "empty"])
def test_pop_consumption_rejects_invalid_supplied_scales(
    needs_economy: Economy, method: str, case: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    scales = needs_economy.calculate_pop_consumption_scales(state)
    if case == "shape":
        scales = np.zeros(4)
    elif case == "empty":
        scales[1, 1] = 1
    else:
        scales[0, 0] = {"negative": -1.0, "nan": np.nan, "inf": np.inf}[case]
    with pytest.raises(ValueError, match="consumption_scales"):
        getattr(needs_economy, method)(state, consumption_scales=scales)


@pytest.mark.parametrize(
    "method", ["calculate_pop_consumption_scales", "calculate_pop_expenses"]
)
@pytest.mark.parametrize("field", ["pops", "pop_wealth"])
def test_pop_consumption_rejects_misaligned_households(
    needs_economy: Economy, consumption_state: EconomyState, method: str, field: str
):
    with pytest.raises(ValueError, match=field):
        getattr(needs_economy, method)(
            _replace_field(consumption_state, field, np.zeros(1))
        )


@pytest.mark.parametrize(
    "method", ["calculate_pop_consumption_scales", "calculate_pop_expenses"]
)
@pytest.mark.parametrize("field", ["pops", "consumption_mult"])
@pytest.mark.parametrize("value", [-1.0, np.inf, np.nan])
def test_pop_consumption_rejects_invalid_population(
    needs_economy: Economy, method: str, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    model = needs_economy
    if field == "pops":
        state = _replace_context(state, pops=np.full((2, 2), value))
    else:
        model = replace(
            model,
            df_pop_types=model.df_pop_types.assign(consumption_mult=[value, 0.05]),
        )
    if field == "consumption_mult" and np.isnan(value):
        np.testing.assert_allclose(
            getattr(model, method)(state), getattr(needs_economy, method)(state)
        )
    else:
        with pytest.raises(ValueError, match=field):
            getattr(model, method)(state)


@pytest.mark.parametrize("case", ["shape", "negative", "nan", "inf"])
def test_pop_expenses_rejects_invalid_prices(needs_economy: Economy, case: str):
    prices = (
        np.zeros(1)
        if case == "shape"
        else np.full(3, {"negative": -1, "nan": np.nan, "inf": np.inf}[case])
    )
    base_state = needs_economy.solve(np.array([1.0, 0.0]))
    state = replace(
        base_state,
        market=replace(base_state.market, market_prices=prices),
    )
    with pytest.raises(ValueError, match="state.market_prices"):
        needs_economy.calculate_pop_expenses(state)


@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_pop_consumption_empty_and_zero_scales(needs_economy: Economy, method: str):
    state = needs_economy.solve(np.zeros(2))
    expected_shape = (3,) if method == "calculate_pop_needs" else (2, 2)
    empty_packages = GoodsBuyPackages(np.array([], dtype=np.int64), np.empty((0, 3)))
    for packages in (None, empty_packages):
        np.testing.assert_array_equal(
            getattr(needs_economy, method)(state, goods_buy_packages=packages),
            np.zeros(expected_shape),
        )
    occupied = _replace_context(state, pops=np.ones((2, 2)))
    with pytest.raises(ValueError, match="pop_wealth tiers.*goods_buy_packages"):
        getattr(needs_economy, method)(
            occupied,
            goods_buy_packages=empty_packages,
            consumption_scales=np.zeros((2, 2)),
        )
    np.testing.assert_array_equal(
        getattr(needs_economy, method)(occupied, consumption_scales=np.zeros((2, 2))),
        np.zeros(expected_shape),
    )


@pytest.mark.parametrize("case", ["scale", "cost", "expenses", "demand"])
def test_pop_consumption_rejects_overflow(needs_economy: Economy, case: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    if case == "scale":
        model = replace(
            needs_economy,
            df_pop_types=needs_economy.df_pop_types.assign(consumption_mult=1e308),
        )
        with pytest.raises(ValueError, match="calculated consumption_scales"):
            model.calculate_pop_consumption_scales(
                _replace_context(state, pops=state.pops * 2)
            )
    elif case == "cost":
        with pytest.raises(ValueError, match="calculated basket costs"):
            needs_economy.calculate_pop_expenses(
                replace(
                    state, market=replace(state.market, market_prices=np.full(3, 1e308))
                )
            )
    else:
        method = (
            "calculate_pop_expenses" if case == "expenses" else "calculate_pop_needs"
        )
        with pytest.raises(ValueError, match="calculated pop_"):
            getattr(needs_economy, method)(
                state, consumption_scales=np.array([[1e308, 0], [0, 0]])
            )


def test_pop_expenses_supplied_baskets_skip_unused_inputs(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    all_packages = needs_economy.calculate_goods_buy_packages(state)
    packages = GoodsBuyPackages(all_packages.wealth[:1], all_packages.quantities[:1])
    scales = needs_economy.calculate_pop_consumption_scales(state)
    changed = _replace_context(
        replace(
            state, households=replace(state.households, pop_needs=np.full(1, np.nan))
        ),
        building_goods_flow=np.full((1, 1), np.nan),
        goods_trade_flow=np.full(1, np.nan),
    )
    model = replace(
        needs_economy,
        df_goods=needs_economy.df_goods.assign(cost=np.nan),
        df_pop_types=needs_economy.df_pop_types.assign(consumption_mult=-1),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
    )
    np.testing.assert_allclose(
        model.calculate_pop_expenses(
            changed, goods_buy_packages=packages, consumption_scales=scales
        ),
        [[200, 0], [0, 0]],
    )


def test_calculate_pop_needs_exact_values_and_snapshot(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    original = {
        name: value.copy()
        for name, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    result = needs_economy.calculate_pop_needs(state)
    np.testing.assert_allclose(result, [0.0, 5.0, 2.5])
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    assert not np.shares_memory(result, state.pop_needs)
    assert result @ needs_economy.base_prices == pytest.approx(200.0)
    for name, value in original.items():
        np.testing.assert_array_equal(_state_arrays(state)[name], value)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state), [0.0, 5.0, 2.5]
    )


def test_calculate_goods_buy_packages_values_schema_and_snapshot(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    arrays = {
        name: value.copy()
        for name, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    source_packages = needs_economy.df_buy_packages.copy(deep=True)
    source_needs = needs_economy.df_pop_needs.copy(deep=True)
    expected = GoodsBuyPackages(
        wealth=np.array([1, 2]),
        quantities=np.array([[0.0, 5.0, 2.5], [0.0, 10.0, 5.0]]),
    )
    result = needs_economy.calculate_goods_buy_packages(state)
    assert isinstance(result, GoodsBuyPackages)
    _assert_goods_buy_packages_equal(result, expected)
    np.testing.assert_allclose(
        result.quantities @ needs_economy.base_prices,
        source_packages.sort_values("wealth")["popneed_food"].to_numpy(),
    )
    for name, value in arrays.items():
        np.testing.assert_array_equal(_state_arrays(state)[name], value)
    pd.testing.assert_frame_equal(needs_economy.df_buy_packages, source_packages)
    pd.testing.assert_frame_equal(needs_economy.df_pop_needs, source_needs)
    for value in (result.wealth, result.quantities):
        assert value.flags.owndata and not value.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            value.flat[0] = 999
    _assert_goods_buy_packages_equal(
        needs_economy.calculate_goods_buy_packages(state), expected
    )


def test_calculate_goods_buy_packages_population_and_profession_independence(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    expected = needs_economy.calculate_goods_buy_packages(state)
    changed = _replace_context(
        replace(
            state,
            market=replace(state.market, market_prices=state.market_prices * 100),
            households=replace(
                state.households,
                pop_wealth=np.full((2, 2), 999, dtype=np.int64),
                pop_needs=np.full(3, 999.0),
            ),
        ),
        pops=np.zeros((2, 2)),
    )
    _assert_goods_buy_packages_equal(
        needs_economy.calculate_goods_buy_packages(changed), expected
    )
    for professions in (
        needs_economy.df_pop_types.assign(consumption_mult=[-1.0, 100.0]),
        needs_economy.df_pop_types.drop(columns="consumption_mult"),
    ):
        model = replace(needs_economy, df_pop_types=professions)
        _assert_goods_buy_packages_equal(
            model.calculate_goods_buy_packages(changed), expected
        )


@pytest.mark.parametrize("source_kind", ["state", "context", "baskets"])
@pytest.mark.parametrize("empty", [False, True])
def test_df_goods_buy_packages_values_and_ownership(
    needs_economy: Economy, source_kind: str, empty: bool
):
    packages = GoodsBuyPackages(
        wealth=np.array([], dtype=np.int64) if empty else np.array([5, 1]),
        quantities=np.empty((0, 3)) if empty else np.array([[4, 5, 6], [1, 2, 3]]),
    )
    initial = needs_economy.solve(np.array([1.0, 0.0]))
    state = _replace_context(initial, goods_buy_packages=packages)
    source = {"state": state, "context": state.context, "baskets": packages}[
        source_kind
    ]
    source_table = needs_economy.df_buy_packages.copy(deep=True)
    expected = pd.DataFrame(
        packages.quantities.copy(),
        index=pd.Index(packages.wealth.copy(), name="wealth"),
        columns=list(needs_economy.goods_index),
    )
    result = needs_economy.df_goods_buy_packages(source)
    pd.testing.assert_frame_equal(result, expected)
    assert result.index.dtype == np.int64
    assert all(dtype == np.float64 for dtype in result.dtypes)
    assert not np.shares_memory(result.to_numpy(), packages.quantities)
    assert not np.shares_memory(result.index.to_numpy(), packages.wealth)
    result.iloc[:, :] = 999
    result.index = pd.Index(np.arange(len(result)), name="changed")
    result.columns = ["changed", "column", "names"]
    pd.testing.assert_frame_equal(needs_economy.df_goods_buy_packages(source), expected)
    pd.testing.assert_frame_equal(needs_economy.df_buy_packages, source_table)
    assert state.goods_buy_packages is packages


def test_df_goods_buy_packages_calculates_from_unprepared_inputs(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    expected = pd.DataFrame(
        [[0.0, 5.0, 2.5], [0.0, 10.0, 5.0]],
        index=pd.Index([1, 2], dtype=np.int64, name="wealth"),
        columns=["unused", "a", "b"],
    )
    for source in (state, state.context):
        pd.testing.assert_frame_equal(
            needs_economy.df_goods_buy_packages(source), expected
        )
    assert state.goods_buy_packages is None


@pytest.mark.parametrize("value", [pd.DataFrame(), np.zeros((1, 3)), None])
def test_df_goods_buy_packages_rejects_invalid_source(needs_economy: Economy, value):
    with pytest.raises(TypeError, match="source must be"):
        needs_economy.df_goods_buy_packages(value)


def test_df_goods_buy_packages_validates_only_goods_alignment(needs_economy: Economy):
    model = replace(
        needs_economy,
        df_buy_packages=pd.DataFrame(),
        df_pop_needs=pd.DataFrame(),
        df_goods=needs_economy.df_goods.assign(cost=np.nan),
    )
    packages = GoodsBuyPackages(np.array([7]), np.array([[1.0, 2.0, 3.0]]))
    np.testing.assert_array_equal(
        model.df_goods_buy_packages(packages).to_numpy(), [[1, 2, 3]]
    )
    with pytest.raises(ValueError, match="columns.*goods_index"):
        model.df_goods_buy_packages(GoodsBuyPackages(np.array([7]), np.zeros((1, 2))))


def test_calculate_goods_buy_packages_aggregate_demand_consistency(
    needs_economy: Economy,
):
    base_state = needs_economy.solve(np.array([1.0, 1.0]))
    state = _replace_context(
        replace(
            base_state,
            households=replace(
                base_state.households, pop_wealth=np.array([[1, 2], [2, 1]])
            ),
        ),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
    )
    packages = needs_economy.calculate_goods_buy_packages(state)
    # Wealth 1: 5,000 workers + 4,000 peasants * 0.05; wealth 2: 3,000 + 2,000 * 0.05.
    expected = packages.quantities[0] * 0.52 + packages.quantities[1] * 0.31
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(state), expected)
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, goods_buy_packages=packages), expected
    )


def test_calculate_pop_needs_custom_packages_scaling_and_snapshot(
    needs_economy: Economy,
):
    base_state = needs_economy.solve(np.array([1.0, 1.0]))
    state = _replace_context(
        replace(
            base_state,
            households=replace(
                base_state.households, pop_wealth=np.array([[1, 2], [2, 1]])
            ),
        ),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
    )
    packages = GoodsBuyPackages(
        wealth=np.array([2.0, 1.0]),
        quantities=np.array([[10, 20, 30], [1, 2, 3]]),
    )
    original = GoodsBuyPackages(packages.wealth, packages.quantities)
    arrays = {
        name: value.copy()
        for name, value in _state_arrays(state).items()
        if isinstance(value, np.ndarray)
    }
    expected = np.array([1, 2, 3]) * 0.52 + np.array([10, 20, 30]) * 0.31
    result = needs_economy.calculate_pop_needs(state, goods_buy_packages=packages)
    np.testing.assert_allclose(result, expected)
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    assert not np.shares_memory(result, packages.quantities)
    for name, value in arrays.items():
        np.testing.assert_array_equal(_state_arrays(state)[name], value)
    _assert_goods_buy_packages_equal(packages, original)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, goods_buy_packages=packages), expected
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(
            _replace_context(state, pops=2 * state.pops), goods_buy_packages=packages
        ),
        2 * expected,
    )
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.drop(columns="consumption_mult"),
    )
    np.testing.assert_allclose(
        model.calculate_pop_needs(state, goods_buy_packages=packages),
        np.array([1, 2, 3]) * 0.9 + np.array([10, 20, 30]) * 0.5,
    )


def test_calculate_pop_needs_supplied_packages_skip_unused_inputs(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_goods_buy_packages(state)
    expected = needs_economy.calculate_pop_needs(state)
    changed = _replace_context(
        replace(
            state,
            market=replace(state.market, market_prices=np.full(3, 999.0)),
            households=replace(state.households, pop_needs=np.full(3, 999.0)),
        ),
        building_goods_flow=np.array([[np.nan]]),
        goods_trade_flow=np.array([np.nan]),
    )
    model = replace(
        needs_economy,
        df_goods=needs_economy.df_goods.drop(columns="cost"),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
    )
    np.testing.assert_allclose(
        model.calculate_pop_needs(changed, goods_buy_packages=packages), expected
    )


def test_calculate_pop_needs_supplied_packages_partial_and_empty(
    needs_economy: Economy,
):
    base_state = needs_economy.solve(np.array([1.0, 0.0]))
    state = replace(
        base_state,
        households=replace(
            base_state.households, pop_wealth=np.array([[7, 0], [999, 0]])
        ),
    )
    packages = GoodsBuyPackages(wealth=np.array([7]), quantities=np.array([[1, 2, 3]]))
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, goods_buy_packages=packages), [1, 2, 3]
    )
    with pytest.raises(ValueError, match="pop_wealth tiers.*goods_buy_packages"):
        needs_economy.calculate_pop_needs(
            replace(
                state,
                households=replace(state.households, pop_wealth=np.full((2, 2), 8)),
            ),
            goods_buy_packages=packages,
        )
    empty = _replace_context(state, pops=np.zeros((2, 2)))
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_needs(
            empty,
            goods_buy_packages=GoodsBuyPackages(
                packages.wealth[:0], packages.quantities[:0]
            ),
        ),
        np.zeros(3),
    )


@pytest.mark.parametrize("width", [0, 2, 4])
@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_pop_consumption_rejects_misaligned_baskets(
    needs_economy: Economy, width: int, method: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = GoodsBuyPackages(np.array([1]), np.zeros((1, width)))
    with pytest.raises(ValueError, match="goods_buy_packages columns.*goods_index"):
        getattr(needs_economy, method)(state, goods_buy_packages=packages)


@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
@pytest.mark.parametrize("value", [pd.DataFrame(), np.zeros((1, 3)), 1])
def test_pop_consumption_rejects_basket_argument_types(
    needs_economy: Economy, method: str, value
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    with pytest.raises(
        TypeError, match="goods_buy_packages must be a GoodsBuyPackages"
    ):
        getattr(needs_economy, method)(state, goods_buy_packages=value)


@pytest.mark.parametrize("field", ["pops", "pop_wealth"])
def test_calculate_pop_needs_supplied_packages_reject_misalignment(
    needs_economy: Economy, field: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_goods_buy_packages(state)
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(
            _replace_field(state, field, np.zeros(1)), goods_buy_packages=packages
        )


@pytest.mark.parametrize("field", ["pops", "consumption_mult"])
@pytest.mark.parametrize("value", [-1.0, np.nan, np.inf])
def test_calculate_pop_needs_supplied_packages_validate_population(
    needs_economy: Economy, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_goods_buy_packages(state)
    model = needs_economy
    if field == "pops":
        state = _replace_context(state, pops=np.full((2, 2), value))
    else:
        model = replace(
            model,
            df_pop_types=model.df_pop_types.assign(consumption_mult=[value, 0.05]),
        )
    if field == "consumption_mult" and np.isnan(value):
        np.testing.assert_allclose(
            model.calculate_pop_needs(state, goods_buy_packages=packages), [0, 5, 2.5]
        )
    else:
        with pytest.raises(ValueError, match=field):
            model.calculate_pop_needs(state, goods_buy_packages=packages)


def test_calculate_pop_needs_professions_wealth_and_scaling(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 1.0]))
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state), [0.0, 5.5, 2.75]
    )
    doubled = _replace_context(state, pops=2 * state.pops)
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(doubled), [0.0, 11.0, 5.5]
    )
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.drop(columns="consumption_mult"),
    )
    np.testing.assert_allclose(model.calculate_pop_needs(state), [0.0, 15.0, 7.5])


@pytest.mark.parametrize(
    ("supply", "weights", "minima", "maxima", "expected"),
    [
        ([100, 100], [1, 2], [0, 0], [1, 1], [10 / 3, 10 / 3]),
        ([900, 100], [1, 1], [0, 0], [0.5, 1], [25 / 3, 5 / 6]),
        ([0, 100], [1, 1], [0.2, 0], [1, 1], [5 / 3, 25 / 6]),
        ([100, 0], [1, 1], [0, 0], [0.5, 1], [10, 0]),
        ([0, 0], [1, 1], [0, 0], [1, 1], [10, 0]),
        ([0, 0], [1, 1], [0.2, 0.1], [1, 1], [20 / 3, 5 / 3]),
        ([100, 100], [0, 0], [0, 0], [1, 1], [10, 0]),
    ],
)
def test_calculate_pop_needs_substitution(
    needs_economy: Economy,
    supply: list[float],
    weights: list[float],
    minima: list[float],
    maxima: list[float],
    expected: list[float],
):
    definitions = needs_economy.df_pop_needs.assign(
        weight=weights, min_supply_share=minima, max_supply_share=maxima
    )
    model = replace(needs_economy, df_pop_needs=definitions)
    state = _replace_context(
        model.solve(np.array([1.0, 0.0])),
        building_goods_flow=np.array([[0.0, *supply], [0.0, 0.0, 0.0]]),
    )
    np.testing.assert_allclose(model.calculate_pop_needs(state), [0.0, *expected])
    np.testing.assert_allclose(
        model.calculate_goods_buy_packages(state).quantities,
        [[0.0, *expected], [0.0, *(2 * value for value in expected)]],
    )


@pytest.mark.parametrize("field", ["imports", "building_goods_flow", "exports"])
def test_calculate_pop_needs_nonpop_market_orders(needs_economy: Economy, field: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    if field == "building_goods_flow":
        value = state.building_goods_flow.copy()
        value[1] = [0.0, -100.0, 0.0]
    else:
        value = np.array([0.0, 100.0, 0.0])
    target = "goods_trade_flow" if field in {"imports", "exports"} else field
    if field == "exports":
        value = -value
    changed = _replace_field(state, target, value)
    expected = [0, 20 / 3, 5 / 3] if field == "imports" else [0, 10 / 3, 10 / 3]
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(changed), expected)
    np.testing.assert_allclose(
        needs_economy.calculate_goods_buy_packages(changed).quantities[0], expected
    )
    if field != "imports":
        oversubscribed = _replace_field(state, target, value * 3)
        if field == "building_goods_flow":
            flow = state.building_goods_flow.copy()
            flow[1] = [0.0, -300.0, 0.0]
            oversubscribed = _replace_context(state, building_goods_flow=flow)
        np.testing.assert_allclose(
            needs_economy.calculate_pop_needs(oversubscribed), [0, 0, 5]
        )
        np.testing.assert_allclose(
            needs_economy.calculate_goods_buy_packages(oversubscribed).quantities[0],
            [0, 0, 5],
        )


def test_calculate_pop_needs_ignores_prices_and_previous_demand(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    changed = replace(
        state,
        market=replace(state.market, market_prices=100 * state.market_prices),
        households=replace(state.households, pop_needs=np.full(3, 999.0)),
    )
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_needs(changed),
        needs_economy.calculate_pop_needs(state),
    )


def test_calculate_pop_needs_single_good_and_overlapping_categories(
    needs_economy: Economy,
):
    definitions = needs_economy.df_pop_needs
    single = definitions.iloc[[0]].assign(key="popneed_clothing")
    model = replace(
        needs_economy,
        df_pop_needs=pd.concat([definitions, single], ignore_index=True),
        df_buy_packages=needs_economy.df_buy_packages.assign(
            popneed_clothing=[80.0, 40.0]
        ),
    )
    state = model.solve(np.array([1.0, 0.0]))
    np.testing.assert_allclose(model.calculate_pop_needs(state), [0, 7, 2.5])
    packages = model.calculate_goods_buy_packages(state)
    np.testing.assert_allclose(packages.quantities, [[0, 7, 2.5], [0, 14, 5]])
    np.testing.assert_allclose(packages.quantities @ model.base_prices, [240, 480])


def test_calculate_pop_needs_zero_population_skips_wealth_lookup(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([0.0, 0.0]))
    empty = replace(
        state,
        households=replace(
            state.households, pop_wealth=np.zeros((2, 2), dtype=np.int64)
        ),
    )
    np.testing.assert_array_equal(needs_economy.calculate_pop_needs(empty), np.zeros(3))
    partial = needs_economy.solve(np.array([1.0, 0.0]))
    partial = replace(
        partial,
        households=replace(partial.households, pop_wealth=np.array([[1, 0], [999, 0]])),
    )
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(partial), [0, 5, 2.5])
    with pytest.raises(ValueError, match="pop_wealth tiers"):
        needs_economy.calculate_pop_needs(
            replace(
                partial,
                households=replace(partial.households, pop_wealth=np.full((2, 2), 3)),
            )
        )


@pytest.mark.parametrize(
    "field",
    [
        "pops",
        "pop_wealth",
        "building_goods_flow",
        "goods_trade_flow",
    ],
)
def test_calculate_pop_needs_rejects_misalignment(needs_economy: Economy, field: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(_replace_field(state, field, np.zeros(1)))
    if field not in {"pops", "pop_wealth"}:
        with pytest.raises(ValueError, match=field):
            needs_economy.calculate_goods_buy_packages(
                _replace_field(state, field, np.zeros(1))
            )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pops", -1.0),
        ("pops", np.nan),
        ("pops", np.inf),
        ("goods_trade_flow", np.nan),
        ("goods_trade_flow", np.inf),
        ("goods_trade_flow", -np.inf),
    ],
)
def test_calculate_pop_needs_rejects_invalid_quantities(
    needs_economy: Economy, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    bad = np.full(getattr(state, field).shape, value)
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(_replace_field(state, field, bad))
    if field != "pops":
        with pytest.raises(ValueError, match=field):
            needs_economy.calculate_goods_buy_packages(
                _replace_field(state, field, bad)
            )


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_calculate_pop_needs_rejects_nonfinite_flows(
    needs_economy: Economy, value: float
):
    state = _replace_context(
        needs_economy.solve(np.array([1.0, 0.0])),
        building_goods_flow=np.full((2, 3), value),
    )
    with pytest.raises(ValueError, match="building_goods_flow"):
        needs_economy.calculate_pop_needs(state)
    with pytest.raises(ValueError, match="building_goods_flow"):
        needs_economy.calculate_goods_buy_packages(state)


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf])
def test_calculate_pop_needs_rejects_invalid_base_prices(
    needs_economy: Economy, value: float
):
    model = replace(
        needs_economy, df_goods=needs_economy.df_goods.assign(cost=[10, value, 40])
    )
    with pytest.raises(ValueError, match="base_prices"):
        model.calculate_pop_needs(model.solve(np.array([1.0, 0.0])))
    with pytest.raises(ValueError, match="base_prices"):
        model.calculate_goods_buy_packages(model.solve(np.array([1.0, 0.0])))


@pytest.mark.parametrize(
    "value", [1.5, -1.0, np.nan, np.inf, float(2**63), 2**63, "bad"]
)
def test_integer_wealth_rejects_invalid_values(
    needs_economy: Economy, value: float | str
):
    with pytest.raises(ValueError, match="pop_wealth"):
        _make_state(pop_wealth=np.array([[value]]))
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.assign(
            start_quality_of_life=[value, 2]
        ),
    )
    with pytest.raises(ValueError, match="pop_wealth_init"):
        _ = model.pop_wealth_init


def test_integer_wealth_owns_storage_and_preserves_int64_boundary():
    source = np.array([[np.iinfo(np.int64).max]], dtype=np.int64)
    state = _make_state(pop_wealth=source)
    source[:] = 0
    assert state.pop_wealth[0, 0] == np.iinfo(np.int64).max
    assert state.pop_wealth.dtype == np.int64
    assert state.pop_wealth.flags.owndata and not state.pop_wealth.flags.writeable
    integral_floats = _make_state(pop_wealth=np.array([[2.0]]))
    np.testing.assert_array_equal(integral_floats.pop_wealth, [[2]])


def test_pop_needs_tables_are_copied_and_cached(needs_economy: Economy):
    needs = needs_economy.df_pop_needs.copy(deep=True)
    packages = needs_economy.df_buy_packages.copy(deep=True)
    model = replace(
        needs_economy, df_pop_needs=needs, df_buy_packages=packages, language="english"
    )
    needs.loc[0, "weight"] = 999
    packages.loc[0, "popneed_food"] = 999
    pd.testing.assert_frame_equal(model.df_pop_needs, needs_economy.df_pop_needs)
    pd.testing.assert_frame_equal(model.df_buy_packages, needs_economy.df_buy_packages)
    data = model._pop_needs_coefficients
    assert data is model._pop_needs_coefficients
    for value in vars(data).values():
        assert value.flags.owndata and not value.flags.writeable
    for name in ("df_pop_needs", "df_buy_packages"):
        with pytest.raises(FrozenInstanceError):
            setattr(model, name, pd.DataFrame())


@pytest.mark.parametrize(
    "case",
    [
        "missing_columns",
        "duplicate_columns",
        "missing_category",
        "missing_good",
        "duplicate_good",
        "no_default",
        "two_defaults",
        "bad_default",
        "negative_weight",
        "non_numeric_weight",
        "nonfinite_share",
        "reversed_shares",
        "large_share",
        "invalid_category",
        "duplicate_wealth",
        "zero_wealth",
        "fractional_wealth",
        "empty_packages",
        "no_categories",
        "negative_package",
        "nonfinite_package",
        "negative_consumption",
        "duplicate_goods_index",
        "duplicate_pop_index",
        "invalid_goods_index",
    ],
)
def test_calculate_pop_needs_rejects_invalid_tables(needs_economy: Economy, case: str):
    needs = needs_economy.df_pop_needs.copy(deep=True)
    packages = needs_economy.df_buy_packages.copy(deep=True)
    professions = needs_economy.df_pop_types.copy(deep=True)
    goods = needs_economy.df_goods.copy(deep=True)
    match = "df_pop_needs"
    if case == "missing_columns":
        needs = needs.drop(columns="weight")
    elif case == "duplicate_columns":
        needs = pd.concat([needs, needs[["weight"]]], axis=1)
    elif case == "missing_category":
        needs["key"] = "popneed_other"
    elif case == "missing_good":
        needs.loc[0, "goods"] = "missing"
    elif case == "duplicate_good":
        needs.loc[1, "goods"] = "a"
    elif case == "no_default":
        needs["is_default"] = False
    elif case == "two_defaults":
        needs["is_default"] = True
    elif case == "bad_default":
        needs["is_default"] = ["yes", "no"]
    elif case == "negative_weight":
        needs.loc[0, "weight"] = -1
    elif case == "non_numeric_weight":
        needs["weight"] = ["bad", "1"]
    elif case == "nonfinite_share":
        needs.loc[0, "min_supply_share"] = np.nan
    elif case == "reversed_shares":
        needs.loc[0, "min_supply_share"] = 0.9
        needs.loc[0, "max_supply_share"] = 0.5
    elif case == "large_share":
        needs.loc[0, "max_supply_share"] = 1.5
    elif case == "invalid_category":
        needs.loc[0, "key"] = None
    elif case in {
        "duplicate_wealth",
        "zero_wealth",
        "fractional_wealth",
        "empty_packages",
        "no_categories",
        "negative_package",
        "nonfinite_package",
    }:
        match = "df_buy_packages"
        if case == "duplicate_wealth":
            packages["wealth"] = [1, 1]
        elif case == "zero_wealth":
            packages["wealth"] = [0, 1]
        elif case == "fractional_wealth":
            packages["wealth"] = [1.5, 1]
        elif case == "empty_packages":
            packages = packages.iloc[:0]
        elif case == "no_categories":
            packages = packages.drop(columns="popneed_food")
        else:
            packages.loc[0, "popneed_food"] = (
                -1 if case == "negative_package" else np.inf
            )
    elif case == "negative_consumption":
        match = "consumption_mult"
        professions["consumption_mult"] = [-1.0, 1.0]
    elif case == "duplicate_goods_index":
        match = "goods_index"
        goods["key"] = ["a", "a", "b"]
    elif case == "duplicate_pop_index":
        match = "pop_index"
        professions["key"] = ["workers", "workers"]
    elif case == "invalid_goods_index":
        match = "goods_index"
        goods["key"] = ["", "a", "b"]
    model = replace(
        needs_economy,
        df_production=needs_economy.df_production.rename(
            columns={"goods_unused": "goods_"} if case == "invalid_goods_index" else {}
        ),
        df_pop_needs=needs,
        df_buy_packages=packages,
        df_pop_types=professions,
        df_goods=goods,
    )
    # Reuse a valid state so malformed table indexes don't affect solve().
    state = needs_economy.solve(np.array([1.0, 0.0]))
    with pytest.raises(ValueError, match=match):
        model.calculate_pop_needs(state)
    if case not in {"negative_consumption", "duplicate_pop_index"}:
        with pytest.raises(ValueError, match=match):
            model.calculate_goods_buy_packages(state)


def test_calculate_pop_needs_vanilla(economy: Economy):
    state = economy.solve(_first_producing_levels(economy))
    needs = economy.calculate_pop_needs(state)
    np.testing.assert_allclose(
        economy.calculate_pop_needs(
            state, goods_buy_packages=economy.calculate_goods_buy_packages(state)
        ),
        needs,
    )
    assert needs.shape == (len(economy.goods_index),)
    assert needs.dtype == np.float64
    assert np.isfinite(needs).all() and (needs >= 0).all() and (needs > 0).any()
    reordered = replace(economy, df_goods=economy.df_goods.iloc[::-1])
    reversed_state = _replace_context(
        replace(
            state,
            market=replace(state.market, market_prices=state.market_prices[::-1]),
            households=replace(state.households, pop_needs=state.pop_needs[::-1]),
        ),
        building_goods_flow=state.building_goods_flow[:, ::-1],
        goods_trade_flow=state.goods_trade_flow[::-1],
    )
    np.testing.assert_allclose(
        reordered.calculate_pop_needs(reversed_state), needs[::-1]
    )


def test_pop_consumption_expenses_vanilla(economy: Economy):
    state = economy.solve(
        _first_producing_levels(economy), method="market", workforce_ratio=0.25
    )
    packages = economy.calculate_goods_buy_packages(state)
    scales = economy.calculate_pop_consumption_scales(state)
    expenses = economy.calculate_pop_expenses(state)
    reused = economy.calculate_pop_expenses(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    needs = economy.calculate_pop_needs(
        state, goods_buy_packages=packages, consumption_scales=scales
    )
    assert expenses.shape == state.pops.shape == scales.shape
    assert expenses.dtype == scales.dtype == np.float64
    assert np.isfinite(expenses).all() and (expenses >= 0).all()
    assert (expenses > 0).any()
    np.testing.assert_allclose(expenses, reused)
    np.testing.assert_allclose(needs, economy.calculate_pop_needs(state))
    assert expenses.sum() == pytest.approx(needs @ state.market_prices)


def test_calculate_goods_buy_packages_vanilla(economy: Economy):
    state = economy.solve(_first_producing_levels(economy))
    packages = economy.calculate_goods_buy_packages(state)
    assert packages.wealth.dtype == np.int64
    np.testing.assert_array_equal(
        packages.wealth, np.sort(economy.df_buy_packages["wealth"].to_numpy())
    )
    assert packages.quantities.shape == (
        len(economy.df_buy_packages),
        len(economy.goods_index),
    )
    values = packages.quantities
    assert values.dtype == np.float64
    assert np.isfinite(values).all() and (values >= 0).all()
    np.testing.assert_allclose(
        values @ economy.base_prices,
        economy.df_buy_packages.sort_values("wealth")["total_popneeds"].to_numpy(),
    )
    reordered = replace(economy, df_goods=economy.df_goods.iloc[::-1])
    reversed_state = _replace_context(
        state,
        building_goods_flow=state.building_goods_flow[:, ::-1],
        goods_trade_flow=state.goods_trade_flow[::-1],
    )
    _assert_goods_buy_packages_equal(
        reordered.calculate_goods_buy_packages(reversed_state),
        GoodsBuyPackages(packages.wealth, packages.quantities[:, ::-1]),
    )


def test_construction_cost_vector(economy):
    cc = economy.construction_cost_vector
    assert cc.shape == (len(economy.df_production),)
    assert cc.dtype == np.float64
    np.testing.assert_array_equal(
        cc, economy.df_production["construction_cost"].to_numpy(dtype=np.float64)
    )


def test_employment_vector(economy):
    emp = economy.employment_vector
    assert emp.shape == (len(economy.df_production),)
    assert emp.dtype == np.float64
    expected = economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    np.testing.assert_array_equal(emp, expected)
    # equals the row sums of the employment matrix.
    np.testing.assert_allclose(emp, economy.employment_matrix.sum(axis=1))


def test_solve_invalid_method(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    with pytest.raises(ValueError, match="Invalid method"):
        economy.solve(levels, method="bogus")


def test_solve_non_1d(economy):
    levels = np.zeros((len(economy.building_index), 1), dtype=np.float64)
    with pytest.raises(ValueError, match="1-D"):
        economy.solve(levels)


def test_solve_wrong_length(economy):
    levels = np.zeros(len(economy.building_index) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="length must match"):
        economy.solve(levels)


def test_solve_trade_flow_wrong_length(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    bad_trade = np.zeros(len(economy.goods_index) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="goods_trade_flow length"):
        economy.solve(levels, goods_trade_flow=bad_trade)


@pytest.mark.parametrize("method", ["nominal", "market", "equilibrium"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_solve_rejects_nonfinite_trade_flow(
    economy: Economy, method: str, value: float
):
    with pytest.raises(ValueError, match="goods_trade_flow.*finite"):
        economy.solve(
            np.zeros(len(economy.building_index)),
            method=method,
            goods_trade_flow=np.full(len(economy.goods_index), value),
        )


def test_solve_rejects_multidimensional_trade_flow(economy: Economy):
    with pytest.raises(ValueError, match="goods_trade_flow.*1-D"):
        economy.solve(
            np.zeros(len(economy.building_index)),
            goods_trade_flow=cast(np.ndarray, np.zeros((len(economy.goods_index), 1))),
        )


def test_solve_nominal(economy):
    n_b = len(economy.building_index)
    n_g = len(economy.goods_index)
    n_p = len(economy.pop_index)
    levels = _first_producing_levels(economy)
    state = economy.solve(levels)
    assert isinstance(state, EconomyState)
    assert state.building_levels.shape == (n_b,)
    assert state.building_goods_flow.shape == (n_b, n_g)
    assert state.building_goods_input.shape == (n_g,)
    assert state.building_goods_output.shape == (n_g,)
    assert state.market_prices.shape == (n_g,)
    assert state.pops.shape == (n_b, n_p)
    assert state.pop_wealth.shape == (n_b, n_p)
    assert state.pop_income is state.pop_expenses is state.pop_balance is None
    assert state.pop_needs.shape == (n_g,)
    np.testing.assert_array_equal(state.goods_trade_flow, np.zeros(n_g))
    assert state.imports.shape == (n_g,)
    assert state.exports.shape == (n_g,)
    np.testing.assert_array_equal(state.market_prices, economy.base_prices)
    np.testing.assert_allclose(
        state.pop_wealth,
        np.broadcast_to(economy.pop_wealth_init, (n_b, n_p)),
    )
    assert np.all(state.imports == 0)
    assert np.all(state.exports == 0)
    assert np.all(state.pop_needs == 0)
    np.testing.assert_allclose(
        state.building_goods_input,
        levels @ economy.goods_input_matrix(),
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        levels @ economy.goods_output_matrix(),
    )
    np.testing.assert_allclose(state.pops, levels[:, None] * economy.employment_matrix)


def test_solve_nominal_pop_needs_and_default(economy: Economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    needs = np.arange(len(economy.goods_index), dtype=np.float64) + 1.0

    default_state = economy.solve(levels)
    explicit_zero_state = economy.solve(
        levels, pop_needs=np.zeros(len(economy.goods_index), dtype=np.float64)
    )
    supplied_state = economy.solve(levels, pop_needs=needs)

    np.testing.assert_array_equal(
        default_state.pop_needs, explicit_zero_state.pop_needs
    )
    np.testing.assert_array_equal(default_state.market_prices, economy.base_prices)
    np.testing.assert_array_equal(supplied_state.pop_needs, needs)
    np.testing.assert_allclose(
        supplied_state.buy_orders,
        supplied_state.building_goods_input + supplied_state.exports + needs,
    )
    np.testing.assert_array_equal(supplied_state.market_prices, economy.base_prices)


@pytest.mark.parametrize(
    "invalid_kind", ["non_1d", "wrong_length", "negative", "nan", "inf"]
)
def test_solve_rejects_invalid_pop_needs(economy: Economy, invalid_kind: str):
    n_goods = len(economy.goods_index)
    pop_needs = np.zeros(n_goods, dtype=np.float64)
    if invalid_kind == "non_1d":
        pop_needs = np.zeros((n_goods, 1), dtype=np.float64)
    elif invalid_kind == "wrong_length":
        pop_needs = np.zeros(n_goods + 1, dtype=np.float64)
    elif invalid_kind == "negative":
        pop_needs[0] = -1.0
    elif invalid_kind == "nan":
        pop_needs[0] = np.nan
    else:
        pop_needs[0] = np.inf
    levels = np.zeros(len(economy.building_index), dtype=np.float64)

    with pytest.raises(ValueError, match="pop_needs"):
        economy.solve(
            levels,
            pop_needs=cast(np.ndarray[tuple[int], np.dtype[np.float64]], pop_needs),
        )


@pytest.mark.parametrize("method", ["nominal", "market"])
def test_solve_with_signed_trade_flow(economy: Economy, method: str):
    n_g = len(economy.goods_index)
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    trade = np.resize(np.array([5.0, -3.0, 0.0]), n_g)
    source = trade.copy()
    state = economy.solve(levels, method=method, goods_trade_flow=trade)
    imports = np.maximum(source, 0)
    exports = np.maximum(-source, 0)
    trade[:] = 999.0
    np.testing.assert_array_equal(state.goods_trade_flow, source)
    np.testing.assert_array_equal(state.imports, imports)
    np.testing.assert_array_equal(state.exports, exports)
    np.testing.assert_allclose(state.sell_orders, state.building_goods_output + imports)
    np.testing.assert_allclose(state.buy_orders, state.building_goods_input + exports)
    assert state.goods_trade_flow is state.context.goods_trade_flow
    for array in (state.goods_trade_flow, state.imports, state.exports):
        assert not array.flags.writeable


def test_solve_with_throughput_multipliers(economy):
    levels = _first_producing_levels(economy)
    multipliers = np.full(len(economy.building_index), 2.0, dtype=np.float64)
    state = economy.solve(levels, throughput_multipliers=multipliers)
    np.testing.assert_allclose(
        state.building_goods_input,
        levels @ economy.goods_input_matrix(multipliers),
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        levels @ economy.goods_output_matrix(multipliers),
    )


def test_economy_of_scale_bonuses_aggregate_configs_and_cap(
    economy: Economy,
) -> None:
    buildings = economy.df_production["building"].astype(str).to_numpy()
    eligible = economy.df_production["economy_of_scale"].to_numpy(dtype=bool)
    building = str(economy.df_production.loc[eligible, "building"].iloc[0])
    positions = np.flatnonzero(buildings == building)
    assert len(positions) >= 2

    levels = np.zeros(len(buildings), dtype=np.float64)
    levels[positions[0]] = 2.5
    levels[positions[1]] = 3.75
    levels[np.flatnonzero(~eligible)[0]] = 10.0
    bonuses = economy.economy_of_scale_bonuses(levels)
    np.testing.assert_allclose(bonuses[positions], 0.0625)
    np.testing.assert_array_equal(bonuses[buildings != building], 0.0)

    capped = economy.economy_of_scale_bonuses(levels, level_cap=5.0)
    np.testing.assert_allclose(capped[positions], 0.05)

    levels[positions] = 0.0
    levels[positions[0]] = 25.0
    np.testing.assert_allclose(economy.economy_of_scale_bonuses(levels)[positions], 0.2)
    np.testing.assert_allclose(
        economy.economy_of_scale_bonuses(levels, level_cap=30.0)[positions], 0.25
    )


def test_building_totals_and_bonuses_share_configuration_aggregation(
    coefficient_economy: Economy,
):
    production = coefficient_economy.df_production.iloc[[1, 0, 1]].copy()
    production["production_method"] = ["first", "second", "third"]
    production["economy_of_scale"] = True
    model = replace(coefficient_economy, df_production=production)
    levels = np.array([1.25, 0.0, 4.0])
    state = model.solve(levels)
    totals = model.levels_per_building(state)
    assert list(totals) == ["factory", "mine"]
    assert totals == {"factory": 5.25, "mine": 0.0}
    np.testing.assert_allclose(
        model.economy_of_scale_bonuses(levels), [0.0525, 0.0, 0.0525]
    )
    np.testing.assert_allclose(
        model.economy_of_scale_bonuses(levels, level_cap=4.0), [0.04, 0.0, 0.04]
    )


@pytest.mark.parametrize("level_cap", [-1.0, np.nan, np.inf])
def test_economy_of_scale_bonuses_reject_invalid_cap(
    economy: Economy, level_cap: float
) -> None:
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    with pytest.raises(ValueError, match="level_cap"):
        economy.economy_of_scale_bonuses(levels, level_cap=level_cap)


def test_economy_of_scale_bonuses_reject_misaligned_levels(
    economy: Economy,
) -> None:
    with pytest.raises(ValueError, match="building_levels shape"):
        economy.economy_of_scale_bonuses(
            np.zeros(len(economy.building_index) + 1, dtype=np.float64)
        )


def test_economy_of_scale_missing_column_and_disabled(economy: Economy) -> None:
    levels = _first_producing_levels(economy)
    without_flag = Economy(
        df_production=economy.df_production.drop(columns="economy_of_scale"),
        df_goods=economy.df_goods,
        df_pop_types=economy.df_pop_types,
    )
    np.testing.assert_array_equal(
        without_flag.economy_of_scale_bonuses(levels), np.zeros(len(levels))
    )

    state = economy.solve(levels, economy_of_scale_level_cap=0.0)
    np.testing.assert_allclose(
        state.building_goods_input, levels @ economy.goods_input_matrix()
    )
    np.testing.assert_allclose(
        state.building_goods_output, levels @ economy.goods_output_matrix()
    )


def test_solve_with_raised_economy_of_scale_cap(economy: Economy) -> None:
    eligible = economy.df_production["economy_of_scale"].to_numpy(dtype=bool)
    position = int(np.flatnonzero(eligible)[0])
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    levels[position] = 25.0

    state = economy.solve(levels, economy_of_scale_level_cap=30.0)
    multipliers = 1.0 + economy.economy_of_scale_bonuses(levels, level_cap=30.0)
    np.testing.assert_allclose(
        state.building_goods_input,
        levels @ economy.goods_input_matrix(multipliers),
    )
    np.testing.assert_allclose(
        state.building_goods_output,
        levels @ economy.goods_output_matrix(multipliers),
    )


def test_solve_market_reuses_flows_and_changes_only_prices(economy: Economy):
    n_b = len(economy.building_index)
    n_g = len(economy.goods_index)
    levels = _first_producing_levels(economy)
    trade = np.resize(np.array([0.5, -0.25, 0.0]), n_g)
    pop_needs = np.full(n_g, 0.75, dtype=np.float64)
    throughput_multipliers = np.full(n_b, 2.0, dtype=np.float64)

    nominal = economy.solve(
        levels,
        goods_trade_flow=trade,
        throughput_multipliers=throughput_multipliers,
        pop_needs=pop_needs,
    )
    market = economy.solve(
        levels,
        method="market",
        goods_trade_flow=trade,
        throughput_multipliers=throughput_multipliers,
        pop_needs=pop_needs,
    )

    np.testing.assert_array_equal(market.building_levels, nominal.building_levels)
    np.testing.assert_allclose(
        market.building_goods_input, nominal.building_goods_input
    )
    np.testing.assert_allclose(
        market.building_goods_output, nominal.building_goods_output
    )
    np.testing.assert_allclose(market.imports, nominal.imports)
    np.testing.assert_allclose(market.exports, nominal.exports)
    np.testing.assert_allclose(market.pops, nominal.pops)
    np.testing.assert_allclose(market.pop_wealth, nominal.pop_wealth)
    assert market.pop_balance is nominal.pop_balance is None
    np.testing.assert_allclose(market.pop_needs, nominal.pop_needs)
    np.testing.assert_allclose(
        market.market_prices,
        economy.market_prices(nominal.buy_orders, nominal.sell_orders),
    )


def test_solve_market_rejects_nonfinite_trade_flow(economy: Economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    invalid_trade = np.full(len(economy.goods_index), np.nan, dtype=np.float64)

    with pytest.raises(ValueError):
        economy.solve(levels, method="market", goods_trade_flow=invalid_trade)


def test_solve_rejects_misaligned_throughput_multipliers(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    with pytest.raises(ValueError, match="throughput_multipliers must be a 1-D"):
        economy.solve(
            levels,
            throughput_multipliers=np.ones((len(levels), 1), dtype=np.float64),
        )
    with pytest.raises(ValueError, match="throughput_multipliers length"):
        economy.solve(
            levels,
            throughput_multipliers=np.ones(len(levels) + 1, dtype=np.float64),
        )


def test_construction_cost(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    levels[0] = 2.0
    levels[1] = 1.0
    state = economy.solve(levels)
    expected = float(np.dot(levels, economy.construction_cost_vector))
    assert economy.construction_cost(state=state) == pytest.approx(expected)


def test_arable_land_consumption(economy: Economy):
    arable_land_groups = {
        "bg_staple_crops",
        "bg_ranching",
        "bg_agriculture",
        "bg_plantations",
        "bg_subsistence_agriculture",
        "bg_subsistence_ranching",
    }
    groups = economy.df_production["building_group"]
    levels = np.zeros(len(groups), dtype=np.float64)
    for group in arable_land_groups:
        group_rows = np.flatnonzero(groups.to_numpy() == group)
        assert len(group_rows) > 0
        levels[group_rows[0]] = 1.0

    staple_crop_rows = np.flatnonzero(groups.to_numpy() == "bg_staple_crops")
    levels[staple_crop_rows[1]] = 2.0

    excluded_row = np.flatnonzero(~groups.isin(tuple(arable_land_groups)).to_numpy())[0]
    levels[excluded_row] = 100.0

    consumption = economy.arable_land_consumption(economy.solve(levels))

    assert consumption == pytest.approx(float(len(arable_land_groups) + 2))
    np.testing.assert_array_equal(
        economy.arable_land_vector,
        groups.isin(tuple(arable_land_groups)).to_numpy(dtype=np.float64),
    )


def test_arable_land_consumption_rejects_misaligned_state(economy: Economy):
    with pytest.raises(ValueError, match="must match the production table"):
        economy.arable_land_consumption(_make_state())


def test_levels_per_building(economy: Economy):
    buildings = economy.df_production["building"].astype(str).to_numpy()
    expected_order = list(dict.fromkeys(buildings))
    first_building = expected_order[0]
    first_building_rows = np.flatnonzero(buildings == first_building)
    levels = np.zeros(len(buildings), dtype=np.float64)
    levels[first_building_rows] = np.arange(
        1, len(first_building_rows) + 1, dtype=np.float64
    )

    totals = economy.levels_per_building(economy.solve(levels))

    assert list(totals) == expected_order
    assert totals[first_building] == pytest.approx(float(np.sum(levels)))
    assert all(totals[building] == 0.0 for building in expected_order[1:])


def test_levels_per_building_rejects_misaligned_state(economy: Economy):
    with pytest.raises(ValueError, match="must match the production table"):
        economy.levels_per_building(_make_state())


def test_market_prices_variance(economy):
    levels = _first_producing_levels(economy)
    state = economy.solve(levels)
    var = economy.market_prices_variance(state=state)
    assert var.shape == (len(economy.goods_index),)
    expected = (state.market_prices / economy.base_prices - 1) * 100
    np.testing.assert_allclose(var, expected)


def test_df_buildings(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    levels[0] = 3.0
    levels[1] = 1.0
    state = economy.solve(levels)
    df = economy.df_buildings(state=state)
    assert list(df.columns) == ["key", "level", "construction_cost"]
    assert (df["level"] > 0).all()
    assert len(df) == 2
    assert df["level"].is_monotonic_decreasing
    expected = pd.DataFrame(
        {
            "key": economy.building_index,
            "level": levels,
            "construction_cost": economy.construction_cost_vector * levels,
        }
    )
    expected = expected[expected["level"] > 0]
    pd.testing.assert_frame_equal(
        df.sort_values("key").reset_index(drop=True),
        expected.sort_values("key").reset_index(drop=True),  # pyright: ignore[reportCallIssue]
    )


def test_df_market(economy):
    levels = _first_producing_levels(economy)
    state = economy.solve(levels)
    df = economy.df_market(state=state)
    expected_cols = [
        "goods",
        "market_prices",
        "market_prices_variance",
        "sell_orders",
        "buy_orders",
        "building_goods_input",
        "building_goods_output",
        "imports",
        "exports",
        "pop_needs",
    ]
    assert list(df.columns) == expected_cols
    assert ((df["sell_orders"] > 0) | (df["buy_orders"] > 0)).all()
    assert df["sell_orders"].is_monotonic_decreasing


def test_employment_by_profession():
    state = _make_state(
        pops=np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]]),
        pop_wealth=np.zeros((2, 3), dtype=np.float64),
    )
    np.testing.assert_array_equal(
        state.employment_by_profession, np.array([10.0, 30.0, 0.0])
    )


def test_total_wealth():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    wealth = np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]])
    state = _make_state(pops=pops, pop_wealth=wealth)
    assert state.total_wealth == pytest.approx(1400.0)


def test_total_wealth_zero_population():
    state = _make_state()
    assert state.total_wealth == 0.0


def test_average_wealth_by_profession():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    wealth = np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]])
    state = _make_state(pops=pops, pop_wealth=wealth)
    np.testing.assert_allclose(
        state.average_wealth_by_profession, np.array([20.0, 40.0, 0.0])
    )
    np.testing.assert_array_equal(
        state.total_wealth_by_profession, [200.0, 1200.0, 0.0]
    )


def test_profession_shares():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    state = _make_state(pops=pops, pop_wealth=np.zeros((2, 3), dtype=np.float64))
    np.testing.assert_allclose(state.profession_shares, np.array([0.25, 0.75, 0.0]))


def test_profession_shares_zero_population():
    state = _make_state()
    np.testing.assert_array_equal(state.profession_shares, np.zeros(3))


def test_wealth_distribution():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    wealth = np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]])
    state = _make_state(pops=pops, pop_wealth=wealth)
    dist = state.wealth_distribution
    assert dist["min"] == pytest.approx(20.0)
    assert dist["max"] == pytest.approx(40.0)
    assert dist["mean"] == pytest.approx(35.0)
    assert dist["median"] == pytest.approx(40.0)
    assert dist["std"] == pytest.approx(np.sqrt(75.0))


def test_wealth_distribution_zero_population():
    state = _make_state()
    assert state.wealth_distribution == {
        "min": 0.0,
        "mean": 0.0,
        "median": 0.0,
        "std": 0.0,
        "max": 0.0,
    }


def test_gini_wealth_equal():
    state = _make_state(
        pops=np.array([[10.0, 10.0]]),
        pop_wealth=np.array([[5.0, 5.0]]),
    )
    assert state.gini_wealth == pytest.approx(0.0)


def test_gini_wealth_max_two_units():
    state = _make_state(
        pops=np.array([[1.0, 1.0]]),
        pop_wealth=np.array([[0.0, 100.0]]),
    )
    assert state.gini_wealth == pytest.approx(0.5)


def test_gini_wealth_zero_population():
    state = _make_state()
    assert state.gini_wealth == 0.0


def test_gini_wealth_zero_wealth():
    state = _make_state(
        pops=np.array([[10.0, 10.0]]),
        pop_wealth=np.array([[0.0, 0.0]]),
    )
    assert state.gini_wealth == 0.0


def test_df_pop(economy):
    levels = _first_producing_levels(economy)
    state = economy.solve(levels)
    df = economy.df_pop(state=state)
    expected_cols = [
        "profession",
        "employment",
        "employment_share",
        "dependents",
        "population",
        "avg_wealth",
        "total_wealth",
        "pop_balance",
    ]
    assert list(df.columns) == expected_cols
    assert (df["employment"] > 0).all()
    assert df["employment"].is_monotonic_decreasing
    assert len(df) <= len(economy.df_pop_types)
    assert df["employment_share"].sum() == pytest.approx(1.0)
    assert set(df["profession"]) <= set(economy.pop_index)
    assert np.allclose(df["avg_wealth"], df["total_wealth"] / df["employment"])


@pytest.mark.parametrize("ratio", [0.0, -0.25, 1.01, np.nan, np.inf, -np.inf])
def test_workforce_ratio_rejects_invalid_values(income_economy: Economy, ratio: float):
    state = _make_state()
    with pytest.raises(ValueError, match="workforce_ratio"):
        _replace_context(state, workforce_ratio=ratio)
    with pytest.raises(ValueError, match="workforce_ratio"):
        income_economy.solve(np.ones(3), workforce_ratio=ratio)


def test_workforce_ratio_population_wealth_and_cached_replacement():
    workers = _make_state(
        pops=np.array([[100.0, 50.0, 0.0], [0, 0, 0], [0, 0, 0]]),
        pop_wealth=np.array([[5, 20, 0], [0, 0, 0], [0, 0, 0]]),
        building_goods_flow=np.array([[100.0, 0, 0], [0, 0, 0], [0, 0, 0]]),
    )
    assert workers.workforce_ratio == 1.0
    assert workers.dependents_per_worker == 0.0
    households = _replace_context(workers, workforce_ratio=0.25)
    assert households.dependents_per_worker == 3.0
    assert "dependents_per_worker" in vars(households.context)
    assert households.total_employment == workers.total_employment == 150.0
    assert households.total_population == 600.0
    assert households.gdp_per_capita() == workers.gdp_per_capita() / 4
    assert households.gdp_per_capita(annual=True) == workers.gdp_per_capita(True) / 4
    assert households.total_wealth == workers.total_wealth * 4
    assert households.average_wealth == workers.average_wealth
    assert households.wealth_distribution == workers.wealth_distribution
    assert households.gini_wealth == workers.gini_wealth
    np.testing.assert_array_equal(
        households.profession_shares, workers.profession_shares
    )
    np.testing.assert_array_equal(
        households.average_wealth_by_profession, workers.average_wealth_by_profession
    )
    assert replace(households).workforce_ratio == 0.25
    changed = _replace_context(households, workforce_ratio=0.5)
    assert changed.dependents_per_worker == 1.0
    assert changed.total_population == 300.0
    assert households.dependents_per_worker == 3.0


@pytest.mark.parametrize("ratio", [1.0, 0.25, 0.6])
@pytest.mark.parametrize("empty", [False, True])
def test_wealth_statistics_and_reports_agree_after_replacement(
    needs_economy: Economy, ratio: float, empty: bool
):
    state = needs_economy.solve(np.ones(2), workforce_ratio=ratio)
    state = _replace_context(
        replace(
            state,
            households=replace(state.households, pop_wealth=np.array([[1, 2], [2, 1]])),
        ),
        pops=np.zeros((2, 2)) if empty else np.array([[2.0, 0.0], [4.0, 3.0]]),
    )
    expected_mean = 0.0 if empty else 13.0 / 9.0
    assert state.average_wealth == pytest.approx(expected_mean)
    assert state.wealth_distribution["mean"] == state.average_wealth
    assert state.total_wealth == pytest.approx(0.0 if empty else 13.0 / ratio)
    np.testing.assert_allclose(
        state.average_wealth_by_profession, [0.0, 0.0] if empty else [10.0 / 6.0, 1.0]
    )
    report = needs_economy.df_pop(state=state)
    assert report["total_wealth"].sum() == pytest.approx(state.total_wealth)
    if not empty:
        assert state.average_wealth == pytest.approx(
            state.total_wealth / state.total_population
        )
        np.testing.assert_allclose(
            report["total_wealth"], report["avg_wealth"] * report["population"]
        )
    changed = replace(
        state, households=replace(state.households, pop_wealth=state.pop_wealth + 1)
    )
    assert changed.average_wealth == pytest.approx(0.0 if empty else expected_mean + 1)
    assert state.average_wealth == pytest.approx(expected_mean)
    assert needs_economy.df_pop(changed)["total_wealth"].sum() == pytest.approx(
        changed.total_wealth
    )


def test_workforce_ratio_empty_population(income_economy: Economy):
    state = income_economy.solve(np.zeros(3), workforce_ratio=0.25)
    assert state.total_employment == state.total_population == 0
    assert state.gdp_per_capita() == 0
    assert state.average_wealth == state.total_wealth == state.gini_wealth == 0
    assert state.wealth_distribution["mean"] == 0
    np.testing.assert_array_equal(state.profession_shares, [0, 0, 0])
    np.testing.assert_array_equal(
        income_economy.calculate_pop_income(state), np.zeros((3, 3))
    )
    assert income_economy.df_pop(state).empty


@pytest.mark.parametrize("method", ["nominal", "market"])
def test_workforce_ratio_consumption_and_reports(needs_economy: Economy, method: str):
    levels = np.array([0.01, 0.0])
    workers = needs_economy.solve(levels, method=method)
    households = needs_economy.solve(levels, method=method, workforce_ratio=0.25)
    assert households.total_employment == 100
    assert households.total_population == 400
    np.testing.assert_array_equal(
        households.building_goods_flow, workers.building_goods_flow
    )
    np.testing.assert_array_equal(households.pop_needs, workers.pop_needs)
    assert households.pop_balance is workers.pop_balance is None
    np.testing.assert_array_equal(households.market_prices, workers.market_prices)
    packages = needs_economy.calculate_goods_buy_packages(workers)
    _assert_goods_buy_packages_equal(
        needs_economy.calculate_goods_buy_packages(households), packages
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(households), [0, 0.125, 0.0625]
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(households, goods_buy_packages=packages),
        2.5 * needs_economy.calculate_pop_needs(workers),
    )
    report = needs_economy.df_pop(households)
    np.testing.assert_array_equal(report["employment"], [100])
    np.testing.assert_array_equal(report["dependents"], [300])
    np.testing.assert_array_equal(report["population"], [400])
    np.testing.assert_allclose(
        report["avg_wealth"], report["total_wealth"] / report["population"]
    )


def test_dependent_income_adds_to_cooperative_income(income_economy: Economy):
    pop_types = income_economy.df_pop_types.copy()
    pop_types["dependent_wage"] = [0.5, 1.0, np.nan]
    model = replace(income_economy, df_pop_types=pop_types)
    workers = model.solve(np.ones(3))
    households = model.solve(np.ones(3), workforce_ratio=0.25)
    cooperative = model.calculate_pop_income(workers)
    expected = cooperative + households.pops * 3 * np.array([0.5, 1, 0]) / 52
    income = model.calculate_pop_income(households)
    np.testing.assert_allclose(income, expected)
    assert income.flags.writeable and income.flags.owndata
    np.testing.assert_array_equal(households.building_surplus, workers.building_surplus)
    np.testing.assert_array_equal(households.building_deficit, workers.building_deficit)
    assert households.gdp_weekly == workers.gdp_weekly
    assert (
        income[1].sum() > 0
    )  # Dependent earnings remain available in a loss-making building.
    assert households.pop_balance is None
    np.testing.assert_array_equal(
        income_economy.calculate_pop_income(households), cooperative
    )  # Missing wage column means zero dependent earnings.


@pytest.mark.parametrize("wage", [-1.0, np.inf, -np.inf, "invalid"])
def test_dependent_income_validates_only_used_wages(income_economy: Economy, wage):
    pop_types = income_economy.df_pop_types.copy()
    pop_types["dependent_wage"] = [wage, 0, 0]
    model = replace(income_economy, df_pop_types=pop_types)
    state = model.solve(np.ones(3), workforce_ratio=0.25)
    with pytest.raises(ValueError, match="dependent_wage"):
        model.calculate_pop_income(state)
    # Worker-only and unoccupied groups do not use the dependent-wage coefficient.
    model.calculate_pop_income(_replace_context(state, workforce_ratio=1.0))
    model.calculate_pop_income(model.solve(np.zeros(3), workforce_ratio=0.25))


def test_dependent_income_rejects_overflow(income_economy: Economy):
    pop_types = income_economy.df_pop_types.copy()
    pop_types["dependent_wage"] = [1e308, 0, 0]
    model = replace(income_economy, df_pop_types=pop_types)
    with pytest.raises(ValueError, match="calculated pop_income"):
        model.calculate_pop_income(model.solve(np.ones(3), workforce_ratio=0.25))


@pytest.mark.parametrize("supply_packages", [False, True])
@pytest.mark.parametrize("supply_scales", [False, True])
def test_prepare_context_reuses_independent_prepared_fields(
    needs_economy: Economy,
    consumption_state: EconomyState,
    supply_packages: bool,
    supply_scales: bool,
):
    packages = needs_economy.calculate_goods_buy_packages(consumption_state)
    scales = needs_economy.calculate_pop_consumption_scales(consumption_state)
    context = replace(
        consumption_state.context,
        goods_buy_packages=GoodsBuyPackages(
            wealth=packages.wealth[::-1],
            quantities=packages.quantities[::-1] * 2,
        )
        if supply_packages
        else None,
        consumption_scales=scales * 3 if supply_scales else None,
    )
    prepared = needs_economy.prepare_context(context)
    assert prepared.goods_buy_packages is not None
    assert prepared.consumption_scales is not None
    assert needs_economy.prepare_context(prepared) is prepared
    assert prepared is not context or supply_packages and supply_scales
    assert (context.goods_buy_packages is not None) == supply_packages
    assert (context.consumption_scales is not None) == supply_scales
    np.testing.assert_array_equal(prepared.goods_buy_packages.wealth, [1, 2])
    np.testing.assert_allclose(
        prepared.goods_buy_packages.quantities,
        packages.quantities * (2 if supply_packages else 1),
    )
    np.testing.assert_allclose(
        prepared.consumption_scales, scales * (3 if supply_scales else 1)
    )
    state = EconomyState(
        context=prepared,
        market=MarketState(prepared, consumption_state.market_prices),
        households=consumption_state.households,
    )
    assert state.goods_buy_packages is prepared.goods_buy_packages
    assert state.consumption_scales is prepared.consumption_scales
    factor = (2 if supply_packages else 1) * (3 if supply_scales else 1)
    needs = needs_economy.calculate_pop_needs(state)
    expenses = needs_economy.calculate_pop_expenses(state)
    np.testing.assert_allclose(
        needs, needs_economy.calculate_pop_needs(consumption_state) * factor
    )
    np.testing.assert_allclose(
        expenses, needs_economy.calculate_pop_expenses(consumption_state) * factor
    )
    assert expenses.sum() == pytest.approx(needs @ state.market_prices)
    for value in (
        prepared.goods_buy_packages.quantities,
        prepared.goods_buy_packages.wealth,
        prepared.consumption_scales,
    ):
        assert value.flags.owndata and not value.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            value.flat[0] = 0

    # Immutable calculators reuse baskets; reports expose independent copies.
    assert (
        needs_economy.calculate_goods_buy_packages(state) is prepared.goods_buy_packages
    )
    assert (
        needs_economy.calculate_goods_buy_packages(prepared)
        is prepared.goods_buy_packages
    )
    frame = needs_economy.df_goods_buy_packages(state)
    pd.testing.assert_frame_equal(frame, needs_economy.df_goods_buy_packages(prepared))
    np.testing.assert_array_equal(frame.index, prepared.goods_buy_packages.wealth)
    assert list(frame.columns) == list(needs_economy.goods_index)
    assert not np.shares_memory(
        frame.to_numpy(), prepared.goods_buy_packages.quantities
    )
    assert not np.shares_memory(
        frame.index.to_numpy(), prepared.goods_buy_packages.wealth
    )
    frame.iloc[:, :] = 999
    for source in (state, prepared):
        result = needs_economy.calculate_pop_consumption_scales(source)
        assert result.flags.owndata and result.flags.writeable
        assert not np.shares_memory(result, prepared.consumption_scales)
        np.testing.assert_array_equal(result, prepared.consumption_scales)
        result[:] = 999


@pytest.mark.parametrize("override_packages", [False, True])
@pytest.mark.parametrize("override_scales", [False, True])
def test_context_consumption_defaults_and_explicit_overrides(
    needs_economy: Economy,
    consumption_state: EconomyState,
    override_packages: bool,
    override_scales: bool,
):
    context = needs_economy.prepare_context(consumption_state.context)
    state = EconomyState(
        context,
        MarketState(context, consumption_state.market_prices),
        consumption_state.households,
    )
    assert context.goods_buy_packages is not None
    packages = (
        replace(
            context.goods_buy_packages,
            quantities=context.goods_buy_packages.quantities * 2,
        )
        if override_packages
        else None
    )
    scales = (
        needs_economy.calculate_pop_consumption_scales(state) * 3
        if override_scales
        else None
    )
    # Prepared inputs bypass coefficients that are no longer needed.
    invalid_model = replace(
        needs_economy,
        df_goods=needs_economy.df_goods.assign(cost=np.nan),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
        df_pop_types=needs_economy.df_pop_types.assign(consumption_mult=-1),
    )
    assert invalid_model.prepare_context(context) is context
    factor = (2 if override_packages else 1) * (3 if override_scales else 1)
    for method in ("calculate_pop_needs", "calculate_pop_expenses"):
        np.testing.assert_allclose(
            getattr(invalid_model, method)(
                state, goods_buy_packages=packages, consumption_scales=scales
            ),
            getattr(needs_economy, method)(consumption_state) * factor,
        )
    assert state.pop_income is state.pop_expenses is state.pop_balance is None


def test_snapshot_replacement_shares_context_and_refreshes_finances(
    needs_economy: Economy, consumption_state: EconomyState
):
    context = needs_economy.prepare_context(consumption_state.context)
    state = EconomyState(
        context,
        MarketState(context, consumption_state.market_prices),
        consumption_state.households,
    )
    old_surplus = state.building_surplus.copy()
    next_state = replace(
        state,
        market=replace(state.market, market_prices=state.market_prices * 2),
        households=replace(state.households, pop_wealth=np.full((2, 2), 2)),
    )
    assert next_state.context is state.context is next_state.market.context
    for name in (
        "building_levels",
        "building_goods_flow",
        "pops",
        "goods_trade_flow",
        "goods_buy_packages",
        "consumption_scales",
        "sell_orders",
        "non_pop_buy_orders",
    ):
        assert getattr(next_state, name) is getattr(state, name)
    np.testing.assert_allclose(next_state.building_surplus, old_surplus * 2)
    np.testing.assert_allclose(state.building_surplus, old_surplus)
    with pytest.raises(ValueError, match="same object"):
        replace(state, context=replace(context))
    for component, name in (
        (state, "context"),
        (state.context, "pops"),
        (state.market, "market_prices"),
        (state.households, "pop_wealth"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(component, name, getattr(component, name))


@pytest.mark.parametrize("income_supplied", [False, True])
@pytest.mark.parametrize("expenses_supplied", [False, True])
def test_optional_household_finances_and_reporting(
    income_economy: Economy, income_supplied: bool, expenses_supplied: bool
):
    state = income_economy.solve(np.ones(3))
    income = income_economy.calculate_pop_income(state)
    expenses = income * 2 + 1
    households = replace(
        state.households,
        pop_income=income if income_supplied else None,
        pop_expenses=expenses if expenses_supplied else None,
    )
    evaluated = replace(state, households=households)
    balance = evaluated.pop_balance
    report = income_economy.df_pop(evaluated)
    if income_supplied and expenses_supplied:
        assert balance is not None
        np.testing.assert_allclose(balance, income - expenses)
        assert balance is households.pop_balance
        assert balance.flags.owndata and not balance.flags.writeable
        expected = pd.Series(balance.sum(axis=0), index=income_economy.pop_index)
        np.testing.assert_allclose(
            report["pop_balance"], expected.loc[report["profession"]]
        )
    else:
        assert balance is None
        assert report["pop_balance"].isna().all()
    for name, supplied, source in (
        ("pop_income", income_supplied, income),
        ("pop_expenses", expenses_supplied, expenses),
    ):
        value = getattr(evaluated, name)
        if supplied:
            assert value.flags.owndata and not value.flags.writeable
            assert not np.shares_memory(value, source)
            source[:] = 999
            assert not (value == 999).any()
        else:
            assert value is None
    assert state.pop_balance is None


@pytest.mark.parametrize("field", ["pop_income", "pop_expenses"])
@pytest.mark.parametrize(
    "value",
    [
        np.zeros(2),
        np.zeros((1, 1)),
        np.full((3, 3), -1),
        np.full((3, 3), np.nan),
        np.full((3, 3), np.inf),
    ],
)
def test_household_finances_reject_invalid_values(field: str, value: np.ndarray):
    with pytest.raises(ValueError, match=field):
        replace(_make_state().households, **{field: value})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"goods_buy_packages": GoodsBuyPackages(np.array([1]), np.zeros((1, 2)))},
            "shape",
        ),
        (
            {
                "goods_buy_packages": GoodsBuyPackages(np.array([1]), np.zeros((1, 3))),
                "goods_trade_flow": np.zeros((1, 3)),
            },
            "shape",
        ),
        ({"consumption_scales": np.zeros(2)}, "shape"),
        ({"consumption_scales": np.full((3, 3), -1)}, "non-negative"),
        ({"consumption_scales": np.full((3, 3), np.inf)}, "finite"),
        ({"consumption_scales": np.ones((3, 3))}, "empty cells"),
    ],
)
def test_context_rejects_invalid_prepared_inputs(changes, message: str):
    with pytest.raises(ValueError, match=message):
        replace(_make_state().context, **changes)


def test_context_rejects_bare_goods_buy_package_array():
    with pytest.raises(TypeError, match="GoodsBuyPackages"):
        replace(_make_state().context, goods_buy_packages=np.zeros((1, 3)))


@pytest.mark.parametrize(
    ("wealth", "quantities", "message"),
    [
        (np.array([0]), np.zeros((1, 3)), "positive wealth"),
        (np.array([1, 1]), np.zeros((2, 3)), "positive wealth"),
        (np.array([[1]]), np.zeros((1, 3)), "positive wealth"),
        (np.array(1), np.zeros((1, 3)), "positive wealth"),
        (np.array([1.5]), np.zeros((1, 3)), "int64"),
        (np.array([-1]), np.zeros((1, 3)), "int64"),
        (np.array([np.inf]), np.zeros((1, 3)), "int64"),
        (np.array([np.nan]), np.zeros((1, 3)), "int64"),
        (np.array(["1"]), np.zeros((1, 3)), "int64"),
        (np.array([2**63], dtype=np.uint64), np.zeros((1, 3)), "int64"),
        (np.array([1, 2]), np.zeros((1, 3)), "shape"),
        (np.array([1]), np.zeros(3), "shape"),
        (np.array([1]), np.array(0), "shape"),
        (np.array([1]), np.zeros((1, 1, 3)), "shape"),
        (np.array([1]), np.full((1, 3), np.nan), "quantities.*finite"),
        (np.array([1]), np.full((1, 3), np.inf), "quantities.*finite"),
        (np.array([1]), np.full((1, 3), -1), "quantities.*non-negative"),
        (np.array([1]), np.full((1, 3), "invalid"), "quantities.*numeric"),
        (
            np.array([1, 2]),
            np.array([[0.0, 1.0, 2.0], [0.0, np.nan, 3.0]]),
            "quantities.*finite",
        ),
    ],
)
def test_goods_buy_packages_reject_invalid_inputs(
    wealth: np.ndarray, quantities: np.ndarray, message: str
):
    with pytest.raises(ValueError, match=message):
        GoodsBuyPackages(wealth=wealth, quantities=quantities)


def test_goods_buy_packages_ownership_sorting_and_context_sharing():
    tiers = np.array([10, 1, 5], dtype=np.int32)
    quantities = np.array([[10, 20, 30], [1, 2, 3], [5, 10, 15]])
    packages = GoodsBuyPackages(wealth=tiers, quantities=quantities)
    tiers[:] = 999
    quantities[:] = 999
    np.testing.assert_array_equal(packages.wealth, [1, 5, 10])
    np.testing.assert_array_equal(
        packages.quantities, [[1, 2, 3], [5, 10, 15], [10, 20, 30]]
    )
    assert packages.wealth.dtype == np.int64
    assert packages.quantities.dtype == np.float64
    for name in ("wealth", "quantities"):
        value = getattr(packages, name)
        assert value.flags.owndata and not value.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            value.flat[0] = 0
        with pytest.raises(FrozenInstanceError):
            setattr(packages, name, value.copy())

    context = replace(_make_state().context, goods_buy_packages=packages)
    assert context.goods_buy_packages is packages
    assert replace(context, workforce_ratio=0.5).goods_buy_packages is packages
    assert replace(context, goods_buy_packages=None).goods_buy_packages is None
    np.testing.assert_array_equal(packages.wealth, [1, 5, 10])


def test_context_prepared_input_ownership():
    state = _make_state(pops=np.ones((3, 3)))
    values = np.array([[4, 5, 6], [1, 2, 3]], dtype=np.float64)
    tiers = np.array([2, 1])
    scales = np.ones((3, 3))
    context = replace(
        state.context,
        goods_buy_packages=GoodsBuyPackages(wealth=tiers, quantities=values),
        consumption_scales=scales,
    )
    values[:] = 999
    tiers[:] = 999
    scales[:] = 999
    assert context.goods_buy_packages is not None
    np.testing.assert_array_equal(
        context.goods_buy_packages.quantities, [[1, 2, 3], [4, 5, 6]]
    )
    np.testing.assert_array_equal(context.goods_buy_packages.wealth, [1, 2])
    np.testing.assert_array_equal(context.consumption_scales, np.ones((3, 3)))


def test_prepared_context_missing_tiers_and_empty_population(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    context = needs_economy.prepare_context(state.context)
    state = EconomyState(
        context,
        MarketState(context, state.market_prices),
        replace(state.households, pop_wealth=np.full((2, 2), 999)),
    )
    for method in ("calculate_pop_needs", "calculate_pop_expenses"):
        with pytest.raises(ValueError, match="pop_wealth tiers.*goods_buy_packages"):
            getattr(needs_economy, method)(state)
    empty = replace(
        context,
        pops=np.zeros((2, 2)),
        consumption_scales=np.zeros((2, 2)),
        goods_buy_packages=GoodsBuyPackages(
            np.array([], dtype=np.int64), np.zeros((0, 3))
        ),
    )
    state = EconomyState(
        empty, MarketState(empty, state.market_prices), state.households
    )
    np.testing.assert_array_equal(needs_economy.calculate_pop_needs(state), np.zeros(3))
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_expenses(state), np.zeros((2, 2))
    )
    assert needs_economy.calculate_goods_buy_packages(empty).wealth.size == 0


def test_prepared_context_checks_goods_alignment(needs_economy: Economy):
    context = replace(
        _make_state().context,
        goods_trade_flow=np.zeros(2),
        goods_buy_packages=GoodsBuyPackages(np.array([1]), np.ones((1, 2))),
    )
    with pytest.raises(ValueError, match="goods_index"):
        needs_economy.calculate_goods_buy_packages(context)


def test_prepared_context_vanilla(economy: Economy):
    state = economy.solve(
        _first_producing_levels(economy), method="market", workforce_ratio=0.25
    )
    context = economy.prepare_context(state.context)
    prepared = EconomyState(
        context, MarketState(context, state.market_prices), state.households
    )
    np.testing.assert_allclose(
        economy.calculate_pop_needs(prepared), economy.calculate_pop_needs(state)
    )
    np.testing.assert_allclose(
        economy.calculate_pop_expenses(prepared), economy.calculate_pop_expenses(state)
    )
    assert context.goods_buy_packages is not None
    assert context.goods_buy_packages.quantities.shape == (
        len(economy.df_buy_packages),
        len(economy.goods_index),
    )


@pytest.fixture
def wealth_economy(needs_economy: Economy) -> Economy:
    """Consumption model with cooperative weights and annual dependent wages."""
    professions = needs_economy.df_pop_types.copy()
    professions["wage_weight"] = [1.0, 2.0]
    professions["dependent_wage"] = [52.0, 104.0]
    return replace(needs_economy, df_pop_types=professions)


@pytest.fixture
def wealth_context() -> EconomyContext:
    """Prepared trade economy with a profitable cooperative and a loss."""
    return EconomyContext(
        building_levels=np.ones(2),
        building_goods_flow=np.array([[0.0, 20.0, -1.0], [0.0, -10.0, 2.0]]),
        goods_trade_flow=np.array([0.0, 3.0, 2.0]),
        pops=np.array([[10_000.0, 5000.0], [5000.0, 0.0]]),
        workforce_ratio=0.5,
        goods_buy_packages=GoodsBuyPackages(
            wealth=np.array([1, 2]),
            quantities=np.array([[0.0, 2.0, 1.0], [0.0, 4.0, 2.0]]),
        ),
        consumption_scales=np.array([[1.0, 0.5], [0.5, 0.0]]),
    )


def test_evaluate_wealth_exact_finances_and_snapshot(
    wealth_economy: Economy, wealth_context: EconomyContext
):
    wealth = np.array([[1.0, 2.0], [2.0, 999.0]])
    source_wealth = wealth.copy()
    source_arrays = {
        name: value.copy()
        for name, value in vars(wealth_context).items()
        if isinstance(value, np.ndarray)
    }
    source_tables = {
        name: getattr(wealth_economy, name).copy(deep=True)
        for name in (
            "df_production",
            "df_goods",
            "df_pop_types",
            "df_pop_needs",
            "df_buy_packages",
        )
    }
    market, households = wealth_economy.evaluate_wealth(wealth_context, wealth)
    state = EconomyState(market.context, market, households)
    assert market.context is wealth_context
    np.testing.assert_array_equal(households.pop_wealth, wealth)
    np.testing.assert_array_equal(households.pop_needs, [0, 6, 3])
    np.testing.assert_allclose(market.market_prices, [10, 215 / 16, 40])
    np.testing.assert_allclose(market.building_surplus, [915 / 4, -435 / 8])
    np.testing.assert_allclose(market.building_deficit, [0, 435 / 8])
    assert households.pop_income is not None
    assert households.pop_expenses is not None
    assert households.pop_balance is not None
    np.testing.assert_allclose(
        households.pop_income, [[10_000 + 915 / 8, 10_000 + 915 / 8], [5000, 0]]
    )
    np.testing.assert_allclose(
        households.pop_expenses, [[535 / 8, 535 / 8], [535 / 8, 0]]
    )
    np.testing.assert_allclose(
        households.pop_balance, households.pop_income - households.pop_expenses
    )
    assert households.pop_expenses.sum() == pytest.approx(
        households.pop_needs @ market.market_prices
    )
    repeated_market, repeated_households = wealth_economy.evaluate_wealth(
        wealth_context, wealth
    )
    repeated = EconomyState(
        repeated_market.context, repeated_market, repeated_households
    )
    for name, value in _state_arrays(state).items():
        np.testing.assert_array_equal(value, _state_arrays(repeated)[name])
        assert not value.flags.writeable
        if name in (
            "market_prices",
            "pop_wealth",
            "pop_needs",
            "pop_income",
            "pop_expenses",
        ):
            assert value.flags.owndata
            assert not np.shares_memory(value, wealth)
    assert households.pop_wealth.dtype == np.int64
    assert households.pop_balance is not None
    assert not households.pop_balance.flags.writeable
    for name, values in source_arrays.items():
        np.testing.assert_array_equal(getattr(wealth_context, name), values)
    for name, frame in source_tables.items():
        pd.testing.assert_frame_equal(getattr(wealth_economy, name), frame)
    np.testing.assert_array_equal(wealth, source_wealth)
    wealth[:] = 0
    np.testing.assert_array_equal(households.pop_wealth, source_wealth)


@pytest.mark.parametrize("supply_packages", [False, True])
@pytest.mark.parametrize("supply_scales", [False, True])
def test_evaluate_wealth_prepares_only_missing_fields(
    wealth_economy: Economy,
    wealth_context: EconomyContext,
    supply_packages: bool,
    supply_scales: bool,
):
    context = replace(
        wealth_context,
        goods_buy_packages=wealth_context.goods_buy_packages
        if supply_packages
        else None,
        consumption_scales=wealth_context.consumption_scales if supply_scales else None,
    )
    wealth = np.array([[1, 2], [2, 999]])
    market, households = wealth_economy.evaluate_wealth(context, wealth)
    prepared = market.context
    assert (prepared is context) == (supply_packages and supply_scales)
    assert prepared.goods_buy_packages is not None
    assert prepared.consumption_scales is not None
    if supply_packages:
        assert prepared.goods_buy_packages is context.goods_buy_packages
    else:
        assert context.goods_buy_packages is None
        np.testing.assert_allclose(
            prepared.goods_buy_packages.quantities,
            wealth_economy.calculate_goods_buy_packages(context).quantities,
        )
    if supply_scales:
        np.testing.assert_array_equal(
            prepared.consumption_scales, context.consumption_scales
        )
    else:
        assert context.consumption_scales is None
        np.testing.assert_allclose(
            prepared.consumption_scales,
            [[1.5, 0.0375], [0.75, 0]],
        )
    assert households.pop_expenses is not None
    assert households.pop_expenses.sum() == pytest.approx(
        households.pop_needs @ market.market_prices
    )


@pytest.mark.parametrize("empty", [False, True])
def test_evaluate_wealth_zero_consumption_and_empty_population(
    wealth_economy: Economy, wealth_context: EconomyContext, empty: bool
):
    context = replace(
        wealth_context,
        consumption_scales=np.zeros((2, 2)),
        pops=np.zeros((2, 2)) if empty else wealth_context.pops,
        building_goods_flow=np.zeros((2, 3))
        if empty
        else wealth_context.building_goods_flow,
        goods_buy_packages=GoodsBuyPackages(
            np.array([], dtype=np.int64), np.zeros((0, 3))
        )
        if empty
        else wealth_context.goods_buy_packages,
    )
    wealth = np.full((2, 2), 999) if empty else np.array([[1, 2], [2, 999]])
    market, households = wealth_economy.evaluate_wealth(context, wealth)
    assert market.context is context
    np.testing.assert_array_equal(households.pop_needs, np.zeros(3))
    np.testing.assert_array_equal(households.pop_expenses, np.zeros((2, 2)))
    if empty:
        np.testing.assert_array_equal(households.pop_income, np.zeros((2, 2)))


@pytest.mark.parametrize(
    ("wealth", "message"),
    [
        (np.ones(2), "pop_wealth shape"),
        (np.ones((2, 1)), "pop_wealth shape"),
        (np.full((2, 2), -1), "non-negative int64"),
        (np.full((2, 2), 1.5), "non-negative int64"),
        (np.full((2, 2), np.nan), "non-negative int64"),
        (np.full((2, 2), np.inf), "non-negative int64"),
        (np.full((2, 2), 2**63, dtype=np.uint64), "non-negative int64"),
        (np.full((2, 2), 999), "pop_wealth tiers.*goods_buy_packages"),
        (np.zeros((2, 2)), "pop_wealth tiers.*goods_buy_packages"),
    ],
)
def test_evaluate_wealth_rejects_invalid_wealth(
    wealth_economy: Economy,
    wealth_context: EconomyContext,
    wealth: np.ndarray,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        wealth_economy.evaluate_wealth(wealth_context, wealth)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"building_goods_flow": np.zeros((1, 3))}, "building_goods_flow shape"),
        ({"building_goods_flow": np.full((2, 3), np.nan)}, "finite"),
        (
            {
                "goods_trade_flow": np.zeros(2),
                "goods_buy_packages": None,
            },
            "context.goods_trade_flow length",
        ),
        ({"goods_trade_flow": np.full(3, np.inf)}, "context.goods_trade_flow.*finite"),
        (
            {
                "goods_trade_flow": np.zeros((1, 3)),
                "goods_buy_packages": None,
            },
            "context.goods_trade_flow.*1-D",
        ),
        ({"pops": np.zeros((1, 2)), "consumption_scales": None}, "pops shape"),
        (
            {"pops": np.full((2, 2), -1), "consumption_scales": None},
            "pops.*non-negative",
        ),
    ],
)
def test_evaluate_wealth_rejects_invalid_context(
    wealth_economy: Economy, wealth_context: EconomyContext, changes, message: str
):
    context = replace(wealth_context, **changes)
    with pytest.raises(ValueError, match=message):
        wealth_economy.evaluate_wealth(context, np.array([[1, 2], [2, 999]]))


def test_evaluate_wealth_propagates_preparation_failure(
    wealth_economy: Economy, wealth_context: EconomyContext
):
    model = replace(wealth_economy, df_buy_packages=pd.DataFrame())
    context = replace(wealth_context, goods_buy_packages=None)
    with pytest.raises(ValueError, match="df_buy_packages"):
        model.evaluate_wealth(context, np.array([[1, 2], [2, 999]]))
    assert context.goods_buy_packages is None
    np.testing.assert_array_equal(
        context.consumption_scales, wealth_context.consumption_scales
    )


def test_evaluate_wealth_propagates_income_failure(
    wealth_economy: Economy, wealth_context: EconomyContext
):
    professions = wealth_economy.df_pop_types.copy()
    professions["wage_weight"] = 0.0
    model = replace(wealth_economy, df_pop_types=professions)
    with pytest.raises(ValueError, match="Positive surplus.*recipient weight"):
        model.evaluate_wealth(wealth_context, np.array([[1, 2], [2, 999]]))


@pytest.fixture
def equilibrium_economy() -> Economy:
    """One food cooperative with a hand-calculable stable second wealth tier."""
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["farm"],
                "production_method": ["pm_farm"],
                "goods_food": [2.1],
                "employment_workers": [10_000.0],
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


@pytest.fixture
def cycling_economy(equilibrium_economy: Economy) -> Economy:
    """Income buys next-tier imports at low demand, but not at high demand."""
    return replace(
        equilibrium_economy,
        df_production=pd.DataFrame(
            {
                "building": ["factory"],
                "production_method": ["pm_factory"],
                "goods_output": [2.5],
                "goods_food": [0.0],
                "employment_workers": [10_000.0],
            }
        ),
        df_goods=pd.DataFrame({"key": ["output", "food"], "cost": [1.0, 1.0]}),
    )


def _assert_evaluated_state(model: Economy, state: EconomyState) -> None:
    """Check every reported quantity against public independent calculators."""
    assert state.pop_income is not None
    assert state.pop_expenses is not None
    assert state.pop_balance is not None
    np.testing.assert_allclose(state.pop_needs, model.calculate_pop_needs(state))
    np.testing.assert_allclose(
        state.market_prices, model.market_prices(state.buy_orders, state.sell_orders)
    )
    np.testing.assert_allclose(state.pop_income, model.calculate_pop_income(state))
    np.testing.assert_allclose(state.pop_expenses, model.calculate_pop_expenses(state))
    np.testing.assert_allclose(state.pop_balance, state.pop_income - state.pop_expenses)
    assert state.pop_expenses.sum() == pytest.approx(
        state.pop_needs @ state.market_prices
    )
    for array in _state_arrays(state).values():
        assert not array.flags.writeable


@pytest.mark.parametrize("starting_tier", [1, 2, 3])
def test_equilibrium_known_solution_and_iteration_boundary(
    equilibrium_economy: Economy, starting_tier: int
):
    initial_wealth = np.array([[starting_tier, 777]])
    initial_copy = initial_wealth.copy()
    result = equilibrium_economy.solve(
        np.ones(1),
        method="equilibrium",
        initial_wealth=initial_wealth,
        max_iterations=1,
    )
    np.testing.assert_array_equal(initial_wealth, initial_copy)
    np.testing.assert_array_equal(result.pop_wealth, [[2, 777]])
    np.testing.assert_allclose(result.pop_needs, [2])
    np.testing.assert_allclose(result.market_prices, [0.9625])
    assert result.pop_income is not None
    assert result.pop_expenses is not None
    np.testing.assert_allclose(result.pop_income, [[2.02125, 0]])
    np.testing.assert_allclose(result.pop_expenses, [[1.925, 0]])
    diagnostics = result.equilibrium_diagnostics
    assert diagnostics == EquilibriumDiagnostics(
        status="converged", iterations=int(starting_tier != 2)
    )
    attribute = "status"
    with pytest.raises(FrozenInstanceError):
        setattr(diagnostics, attribute, "cycle")
    _assert_evaluated_state(equilibrium_economy, result)
    new_market, new_households = equilibrium_economy.iterate(
        result.context, result.market, result.households
    )
    assert new_market is result.market
    assert new_households is result.households


def test_equilibrium_default_wealth_and_legacy_modes(equilibrium_economy: Economy):
    result = equilibrium_economy.solve(np.ones(1), method="equilibrium")
    np.testing.assert_array_equal(result.pop_wealth, [[2, 999]])
    for method in ("nominal", "market"):
        original = equilibrium_economy.solve(np.ones(1), method=method)
        ignored = equilibrium_economy.solve(
            np.ones(1),
            method=method,
            initial_wealth=np.array([[3, 0]]),
            max_iterations=0,
            rtol=-1,
            atol=-1,
        )
        for name, array in _state_arrays(original).items():
            np.testing.assert_array_equal(array, _state_arrays(ignored)[name])
        assert original.equilibrium_diagnostics is None
        assert ignored.equilibrium_diagnostics is None


@pytest.mark.parametrize(
    ("tier", "income", "rtol", "atol", "expected"),
    [
        (2, 1.96, 0.0, 0.0, 2),  # Strict decrease: equality holds.
        (2, 1.95, 0.0, 0.0, 1),
        (2, 3.06, 0.0, 0.0, 3),  # Inclusive advancement equality.
        (2, 3.05, 0.0, 0.0, 2),
        (2, 1.95, 0.0, 0.02, 2),
        (2, 1.95, 0.01, 0.0, 2),
        (2, 3.05, 0.0, 0.02, 3),
        (2, 3.05, 0.01, 0.0, 3),
        (1, 0.0, 0.0, 0.0, 1),  # Unaffordable floor stays bounded.
        (3, 100.0, 0.0, 0.0, 3),
    ],
)
def test_iterate_thresholds_and_tolerance(
    equilibrium_economy: Economy,
    tier: int,
    income: float,
    rtol: float,
    atol: float,
    expected: int,
):
    initial = equilibrium_economy.solve(np.ones(1))
    context = equilibrium_economy.prepare_context(initial.context)
    market = MarketState(context, np.ones(1))
    households = PopState(
        np.array([[tier, 999]]),
        np.array([float(tier)]),
        np.array([[income, 0.0]]),
        np.array([[float(tier), 0.0]]),
    )
    market_after, households_after = equilibrium_economy.iterate(
        context, market, households, rtol=rtol, atol=atol
    )
    np.testing.assert_array_equal(households_after.pop_wealth, [[expected, 999]])
    assert market_after.context is context
    if expected == tier:
        assert market_after is market
        assert households_after is households
    else:
        _assert_evaluated_state(
            equilibrium_economy, EconomyState(context, market_after, households_after)
        )
    np.testing.assert_array_equal(households.pop_wealth, [[tier, 999]])


def test_iterate_simultaneous_changes_and_nonmonotonic_costs(
    wealth_economy: Economy, wealth_context: EconomyContext
):
    context = replace(
        wealth_context,
        goods_buy_packages=GoodsBuyPackages(
            wealth=np.array([1, 2, 3]),
            quantities=np.array([[0.0, 2.0, 0.0], [0.0, 10.0, 0.0], [0.0, 1.0, 0.0]]),
        ),
    )
    market = MarketState(context, np.ones(3))
    households = PopState(
        np.array([[2, 1], [2, 999]]),
        np.zeros(3),
        np.array([[5.0, 10.0], [5.0, 0.0]]),
        np.zeros((2, 2)),
    )
    next_market, next_households = wealth_economy.iterate(
        context, market, households, rtol=0, atol=0
    )
    # Cell (0, 0) can afford the cheaper next tier but must decrease first.
    np.testing.assert_array_equal(next_households.pop_wealth, [[1, 2], [3, 999]])
    assert next_market.context is context
    _assert_evaluated_state(
        wealth_economy, EconomyState(context, next_market, next_households)
    )


def test_iterate_zero_consumption_and_empty_population(equilibrium_economy: Economy):
    initial = equilibrium_economy.solve(np.ones(1))
    context = replace(
        equilibrium_economy.prepare_context(initial.context),
        consumption_scales=np.zeros((1, 2)),
    )
    market, households = equilibrium_economy.evaluate_wealth(
        context, initial.pop_wealth
    )
    next_market, next_households = equilibrium_economy.iterate(
        context, market, households
    )
    np.testing.assert_array_equal(next_households.pop_wealth, [[2, 999]])
    np.testing.assert_array_equal(next_households.pop_expenses, [[0, 0]])
    _assert_evaluated_state(
        equilibrium_economy, EconomyState(context, next_market, next_households)
    )
    empty_context = replace(
        context,
        building_levels=np.zeros(1),
        building_goods_flow=np.zeros((1, 1)),
        pops=np.zeros((1, 2)),
        goods_buy_packages=GoodsBuyPackages(np.array([], dtype=int), np.empty((0, 1))),
    )
    empty_market, empty_households = equilibrium_economy.evaluate_wealth(
        empty_context, np.array([[777, 888]])
    )
    same_market, same_households = equilibrium_economy.iterate(
        empty_context, empty_market, empty_households
    )
    assert same_market is empty_market
    assert same_households is empty_households
    result = equilibrium_economy.solve(np.zeros(1), method="equilibrium")
    assert result.equilibrium_diagnostics == EquilibriumDiagnostics("converged", 0)
    _assert_evaluated_state(equilibrium_economy, result)


def test_equilibrium_dependents_and_financial_flags(equilibrium_economy: Economy):
    professions = equilibrium_economy.df_pop_types.copy()
    professions["dependent_wage"] = [52 / 10_000, 0.0]
    model = replace(equilibrium_economy, df_pop_types=professions)
    result = model.solve(np.ones(1), method="equilibrium", workforce_ratio=0.25)
    np.testing.assert_array_equal(result.pop_wealth, [[1, 999]])
    assert result.consumption_scales is not None
    assert result.pop_income is not None
    np.testing.assert_allclose(result.consumption_scales, [[2.5, 0]])
    np.testing.assert_allclose(result.pop_income, [[2.4 + 3, 0]])
    _assert_evaluated_state(model, result)

    production = equilibrium_economy.df_production.copy()
    production["goods_food"] = [-1.0]
    loss_model = replace(equilibrium_economy, df_production=production)
    flagged = loss_model.solve(
        np.ones(1), method="equilibrium", goods_trade_flow=np.array([10.0])
    )
    assert flagged.equilibrium_diagnostics == EquilibriumDiagnostics(
        "converged",
        0,
        unaffordable_floor_cells=((0, 0),),
        loss_buildings=(0,),
    )
    _assert_evaluated_state(loss_model, flagged)
    no_material_loss = loss_model.solve(
        np.ones(1), method="equilibrium", goods_trade_flow=np.array([10.0]), atol=0.3
    )
    assert no_material_loss.equilibrium_diagnostics == EquilibriumDiagnostics(
        "converged", 0
    )


@pytest.mark.parametrize(
    ("initial_tier", "budget", "status", "iterations", "cycle_start"),
    [
        (1, 1, "max_iterations", 1, None),
        (1, 2, "cycle", 2, 0),
        (1, 10, "cycle", 2, 0),
        (3, 3, "cycle", 3, 1),
    ],
)
def test_equilibrium_cycle_and_exhaustion(
    cycling_economy: Economy,
    initial_tier: int,
    budget: int,
    status: str,
    iterations: int,
    cycle_start: int | None,
):
    with pytest.raises(EquilibriumError) as caught:
        cycling_economy.solve(
            np.ones(1),
            method="equilibrium",
            goods_trade_flow=np.array([-2.5, 1.0]),
            initial_wealth=np.array([[initial_tier, 999]]),
            max_iterations=budget,
        )
    error = caught.value
    assert error.diagnostics is error.state.equilibrium_diagnostics
    assert error.diagnostics.status == status
    assert error.diagnostics.iterations == iterations
    assert error.diagnostics.cycle_start == cycle_start
    assert error.diagnostics.cycle_length == (None if cycle_start is None else 2)
    assert error.diagnostics.increasing_cells or error.diagnostics.decreasing_cells
    _assert_evaluated_state(cycling_economy, error.state)
    with pytest.raises(ValueError, match="read-only"):
        error.state.pop_wealth[0, 0] = 3


def test_equilibrium_evaluation_failure_preserves_preceding_state(
    cycling_economy: Economy,
):
    production = pd.DataFrame(
        {
            "building": ["factory", "unemployed"],
            "production_method": ["pm_factory", "pm_trade"],
            "goods_output": [2.5, -1.2],
            "goods_food": [0.0, 1.0],
            "employment_workers": [10_000.0, 0.0],
        }
    )
    model = replace(cycling_economy, df_production=production)
    with pytest.raises(
        EquilibriumError, match="no positive recipient weight"
    ) as caught:
        model.solve(
            np.ones(2), method="equilibrium", goods_trade_flow=np.array([-1.3, 0.0])
        )
    error = caught.value
    assert error.diagnostics.status == "evaluation_failed"
    assert error.diagnostics.iterations == 0
    assert error.diagnostics.increasing_cells == ((0, 0),)
    assert error.diagnostics.loss_buildings == (1,)
    assert isinstance(error.__cause__, ValueError)
    np.testing.assert_array_equal(error.state.pop_wealth, [[1, 999], [1, 999]])
    _assert_evaluated_state(model, error.state)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("rtol", -1.0),
        ("rtol", float("nan")),
        ("rtol", float("inf")),
        ("rtol", True),
        ("atol", -1.0),
        ("atol", float("nan")),
        ("atol", float("inf")),
        ("atol", True),
        ("max_iterations", 0),
        ("max_iterations", -1),
        ("max_iterations", 1.5),
        ("max_iterations", True),
    ],
)
def test_equilibrium_rejects_invalid_controls(
    equilibrium_economy: Economy, name: str, value
):
    with pytest.raises(ValueError, match=name):
        equilibrium_economy.solve(np.ones(1), method="equilibrium", **{name: value})


@pytest.mark.parametrize(
    "wealth",
    [
        np.array([1, 2]),
        np.array([[0, 999]]),
        np.array([[4, 999]]),
        np.array([[1.5, 999]]),
        np.array([[-1, 999]]),
        np.array([[np.nan, 999]]),
    ],
)
def test_equilibrium_rejects_invalid_initial_wealth(
    equilibrium_economy: Economy, wealth: np.ndarray
):
    with pytest.raises(ValueError, match="pop_wealth"):
        equilibrium_economy.solve(
            np.ones(1), method="equilibrium", initial_wealth=wealth
        )


def test_equilibrium_rejects_explicit_needs_and_nonconsecutive_tiers(
    equilibrium_economy: Economy,
):
    with pytest.raises(ValueError, match="endogenous"):
        equilibrium_economy.solve(
            np.ones(1), method="equilibrium", pop_needs=np.zeros(1)
        )
    model = replace(
        equilibrium_economy,
        df_buy_packages=equilibrium_economy.df_buy_packages.iloc[[0, 2]],
    )
    with pytest.raises(ValueError, match="consecutive"):
        model.solve(np.ones(1), method="equilibrium")
    # Fixed-wealth evaluation still supports sparse labels.
    initial = model.solve(np.ones(1))
    model.evaluate_wealth(initial.context, initial.pop_wealth)


@pytest.mark.parametrize(
    "case",
    [
        "identity",
        "unprepared",
        "income",
        "expenses",
        "wealth",
        "prices",
        "needs",
        "empty_tiers",
        "negative_levels",
    ],
)
def test_iterate_rejects_invalid_components(equilibrium_economy: Economy, case: str):
    initial = equilibrium_economy.solve(np.ones(1))
    market, households = equilibrium_economy.evaluate_wealth(
        initial.context, initial.pop_wealth
    )
    context = market.context
    if case == "identity":
        context = replace(context)
    elif case == "unprepared":
        context = initial.context
        market = replace(market, context=context)
    elif case in ("income", "expenses"):
        households = replace(households, **{f"pop_{case}": None})
    elif case == "wealth":
        households = PopState(
            np.zeros((2, 2), dtype=int), np.ones(1), np.zeros((2, 2)), np.zeros((2, 2))
        )
    elif case == "prices":
        market = replace(market, market_prices=np.array([np.nan]))
    elif case == "needs":
        households = replace(households, pop_needs=np.ones(2))
    elif case == "empty_tiers":
        context = replace(
            context,
            goods_buy_packages=GoodsBuyPackages(
                np.array([], dtype=int), np.empty((0, 1))
            ),
        )
        market = replace(market, context=context)
    elif case == "negative_levels":
        context = replace(context, building_levels=-np.ones(1))
        market = replace(market, context=context)
    with pytest.raises(ValueError):
        equilibrium_economy.iterate(context, market, households)


def test_equilibrium_verification_rejects_inconsistent_public_accounting(
    equilibrium_economy: Economy,
):
    class InconsistentDemandEconomy(Economy):
        """An extension whose reporting disagrees with the solver's demand."""

        def calculate_pop_needs(
            self,
            state: EconomyState,
            *,
            goods_buy_packages: GoodsBuyPackages | None = None,
            consumption_scales: np.ndarray | None = None,
        ) -> np.ndarray:
            return (
                super().calculate_pop_needs(
                    state,
                    goods_buy_packages=goods_buy_packages,
                    consumption_scales=consumption_scales,
                )
                + 0.5
            )

    model = InconsistentDemandEconomy(
        df_production=equilibrium_economy.df_production,
        df_goods=equilibrium_economy.df_goods,
        df_pop_types=equilibrium_economy.df_pop_types,
        df_pop_needs=equilibrium_economy.df_pop_needs,
        df_buy_packages=equilibrium_economy.df_buy_packages,
    )
    with pytest.raises(EquilibriumError, match="verification disagrees") as caught:
        model.solve(np.ones(1), method="equilibrium")
    assert caught.value.diagnostics.status == "verification_failed"
    assert caught.value.diagnostics.iterations == 1
    assert isinstance(caught.value.__cause__, ValueError)
    # The retained state remains the last complete evaluation, not the inconsistent report.
    _assert_evaluated_state(equilibrium_economy, caught.value.state)


def test_equilibrium_verification_rechecks_transitions_within_tolerance(
    equilibrium_economy: Economy,
):
    class RevisedIncomeEconomy(Economy):
        """Small reporting difference accepted numerically but changing stationarity."""

        def calculate_pop_income(self, state: EconomyState) -> np.ndarray:
            return np.maximum(super().calculate_pop_income(state) - 0.015, 0)

    production = equilibrium_economy.df_production.copy()
    production["goods_food"] = [1.95]
    model = RevisedIncomeEconomy(
        df_production=production,
        df_goods=equilibrium_economy.df_goods,
        df_pop_types=equilibrium_economy.df_pop_types,
        df_pop_needs=equilibrium_economy.df_pop_needs,
        df_buy_packages=equilibrium_economy.df_buy_packages,
    )
    with pytest.raises(
        EquilibriumError, match="requires further wealth transitions"
    ) as caught:
        model.solve(
            np.ones(1),
            method="equilibrium",
            initial_wealth=np.array([[2, 999]]),
            rtol=0,
            atol=0.02,
        )
    assert caught.value.diagnostics.status == "verification_failed"
    assert caught.value.diagnostics.iterations == 0
    assert isinstance(caught.value.__cause__, ValueError)


def test_equilibrium_runtime_overflow_preserves_last_state(cycling_economy: Economy):
    packages = cycling_economy.df_buy_packages.copy()
    packages["popneed_food"] = [1.0, 2.0, 1.05e308]
    model = replace(cycling_economy, df_buy_packages=packages)
    with pytest.raises(EquilibriumError, match="transition basket costs") as caught:
        model.solve(
            np.ones(1),
            method="equilibrium",
            goods_trade_flow=np.array([-2.5, 1.0]),
        )
    assert caught.value.diagnostics.status == "evaluation_failed"
    assert caught.value.diagnostics.iterations == 0
    assert caught.value.diagnostics.increasing_cells == ((0, 0),)
    np.testing.assert_array_equal(caught.value.state.pop_wealth, [[1, 999]])
    assert isinstance(caught.value.__cause__, ValueError)
    _assert_evaluated_state(model, caught.value.state)


def test_iterate_top_tier_omits_unused_advancement_threshold(
    equilibrium_economy: Economy,
):
    initial = equilibrium_economy.solve(np.ones(1))
    context = replace(
        equilibrium_economy.prepare_context(initial.context),
        goods_buy_packages=GoodsBuyPackages(
            wealth=np.array([1, 2, 3]), quantities=np.array([[1.0], [2.0], [1.78e308]])
        ),
    )
    market = MarketState(context, np.ones(1))
    households = PopState(
        np.array([[3, 999]]),
        np.array([1.78e308]),
        np.array([[1.78e308, 0.0]]),
        np.array([[1.78e308, 0.0]]),
    )
    next_market, next_households = equilibrium_economy.iterate(
        context, market, households
    )
    assert next_market is market
    assert next_households is households


def test_equilibrium_initial_calculation_errors_remain_value_errors(
    equilibrium_economy: Economy,
):
    professions = equilibrium_economy.df_pop_types.copy()
    professions["wage_weight"] = [0.0, 0.0]
    model = replace(equilibrium_economy, df_pop_types=professions)
    with pytest.raises(ValueError, match="no positive recipient weight"):
        model.solve(np.ones(1), method="equilibrium")
    with pytest.raises(ValueError, match="requires state diagnostics"):
        EquilibriumError("failure", equilibrium_economy.solve(np.ones(1)))


def test_equilibrium_vanilla(economy: Economy):
    try:
        result = economy.solve(
            _first_producing_levels(economy),
            method="equilibrium",
            workforce_ratio=0.25,
            max_iterations=3,
        )
    except EquilibriumError as error:
        result = error.state
        assert error.diagnostics.status in {"cycle", "max_iterations"}
    assert result.equilibrium_diagnostics is not None
    assert result.pop_wealth.dtype == np.int64
    assert result.pop_income is not None
    assert result.pop_expenses is not None
    _assert_evaluated_state(economy, result)


def test_evaluate_wealth_vanilla(economy: Economy):
    initial = economy.solve(_first_producing_levels(economy), workforce_ratio=0.25)
    market, households = economy.evaluate_wealth(initial.context, initial.pop_wealth)
    state = EconomyState(market.context, market, households)
    assert state.context is not initial.context
    assert initial.context.goods_buy_packages is None
    assert initial.context.consumption_scales is None
    assert state.context.goods_buy_packages is not None
    assert state.context.consumption_scales is not None
    assert market.market_prices.shape == (len(economy.goods_index),)
    assert households.pop_needs.shape == (len(economy.goods_index),)
    np.testing.assert_array_equal(households.pop_wealth, initial.pop_wealth)
    assert households.pop_wealth.dtype == np.int64
    for values in (
        households.pop_income,
        households.pop_expenses,
        households.pop_balance,
    ):
        assert values is not None
        assert values.shape == initial.pops.shape
        assert values.dtype == np.float64
        assert np.isfinite(values).all()
        assert not values.flags.writeable
    assert households.pop_income is not None
    assert households.pop_expenses is not None
    assert households.pop_balance is not None
    np.testing.assert_allclose(
        households.pop_balance, households.pop_income - households.pop_expenses
    )
    assert households.pop_expenses.sum() == pytest.approx(
        households.pop_needs @ market.market_prices
    )
