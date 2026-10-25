# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import FrozenInstanceError, replace
from typing import cast

import numpy as np
import pandas as pd
import pytest

from vic3_analysis.analysis.economy import Economy, EconomyState


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


def test_missing_goods_columns_warn_and_cache_zero_flows(coefficient_economy: Economy):
    with pytest.warns(UserWarning, match="Missing goods input columns.*goods_tools"):
        model = Economy(
            df_production=coefficient_economy.df_production.drop(columns="goods_tools"),
            df_goods=coefficient_economy.df_goods,
            df_pop_types=coefficient_economy.df_pop_types,
        )
    np.testing.assert_array_equal(
        model.goods_input_matrix_unscaled, [[0.0, 0.0], [3.0, 0.0]]
    )
    np.testing.assert_array_equal(
        model.goods_output_matrix_unscaled, [[5.0, 0.0], [0.0, 0.0]]
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
    imports=None,
    exports=None,
    market_prices=None,
    pops=None,
    pop_wealth=None,
    pop_needs=None,
) -> EconomyState:
    n = 3
    z = np.zeros(n, dtype=np.float64)
    return EconomyState(
        building_levels=z,
        building_goods_flow=building_goods_flow
        if building_goods_flow is not None
        else np.zeros((n, n), dtype=np.float64),
        imports=imports if imports is not None else z,
        exports=exports if exports is not None else z,
        market_prices=market_prices
        if market_prices is not None
        else np.ones(n, dtype=np.float64),
        pops=pops if pops is not None else np.zeros((n, n), dtype=np.float64),
        pop_wealth=pop_wealth
        if pop_wealth is not None
        else np.zeros((n, n), dtype=np.float64),
        pop_balance=np.zeros((n, n), dtype=np.float64),
        pop_needs=pop_needs if pop_needs is not None else z,
    )


def test_state_defensively_copies_and_freezes_input_arrays():
    source = np.arange(9, dtype=np.float64).reshape(3, 3)
    state = _make_state(building_goods_flow=source)

    source[0, 0] = 999.0

    assert state.building_goods_flow[0, 0] == 0.0
    for name in (
        "building_levels",
        "building_goods_flow",
        "imports",
        "exports",
        "market_prices",
        "pops",
        "pop_wealth",
        "pop_balance",
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
        "wealth_by_profession",
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
    repriced = replace(state, market_prices=np.array([1, 10, 1]))
    np.testing.assert_array_equal(repriced.building_surplus, [-10, 22, 0])
    np.testing.assert_array_equal(repriced.building_deficit, [10, 0, 0])
    changed = replace(state, building_goods_flow=-state.building_goods_flow)
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
        for name, value in vars(state).items()
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
        np.testing.assert_array_equal(getattr(state, name), value)
        assert not np.shares_memory(result, getattr(state, name))
    pd.testing.assert_frame_equal(income_economy.df_pop_types, source_pops)
    pd.testing.assert_frame_equal(income_economy.df_production, source_production)
    result[:] = 999
    np.testing.assert_array_equal(income_economy.calculate_pop_income(state), expected)


def test_calculate_pop_income_uses_stored_flows_prices_and_separate_configs(
    income_economy: Economy,
):
    state = replace(
        income_economy.solve(np.zeros(3)),
        building_goods_flow=np.array([[40, -10], [20, -10], [0, 0]]),
        market_prices=np.array([20, 10]),
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
        reordered.calculate_pop_income(replace(state, pops=state.pops[:, ::-1])),
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
        state = replace(state, pops=np.zeros_like(state.pops))
    with pytest.raises(
        ValueError, match="no positive recipient weight.*factory\\+pm_one"
    ):
        model.calculate_pop_income(state)
    state = replace(state, building_goods_flow=np.array([[-1, 0], [0, 0], [0, 0]]))
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
    state = replace(income_economy.solve(np.ones(3)), **{field: value})
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
        state = replace(state, pops=np.full((3, 3), 1e308))
    elif case == "total_weight":
        model = replace(model, df_pop_types=model.df_pop_types.assign(wage_weight=1))
        state = replace(state, pops=np.full((3, 3), 1e308))
    else:
        state = replace(state, market_prices=np.full(2, 1e308))
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
        imports=np.array([2.0, 1.0, 0.0]),
    )
    np.testing.assert_array_equal(state.sell_orders, np.array([12.0, 1.0, 5.0]))


def test_buy_orders():
    state = _make_state(
        building_goods_flow=np.array([[-3.0, 0.0, -1.0], [0, 0, 0], [0, 0, 0]]),
        exports=np.array([0.0, 2.0, 1.0]),
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
    return replace(
        needs_economy.solve(np.array([1.0, 1.0])),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
        pop_wealth=np.array([[1, 2], [2, 1]]),
        market_prices=np.array([10.0, 40.0, 20.0]),
    )


@pytest.mark.parametrize("workforce_ratio", [1.0, 0.25])
def test_pop_consumption_scales_values_and_ownership(
    needs_economy: Economy, consumption_state: EconomyState, workforce_ratio: float
):
    state = replace(consumption_state, workforce_ratio=workforce_ratio)
    original = {
        key: value.copy()
        for key, value in vars(state).items()
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
        np.testing.assert_array_equal(getattr(state, key), value)
    assert not np.shares_memory(result, state.pops)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_consumption_scales(state), expected
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_consumption_scales(
            replace(state, pops=2 * state.pops)
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
    changed = replace(
        consumption_state,
        pop_wealth=np.full((2, 2), 999),
        market_prices=np.full(3, np.nan),
        building_goods_flow=np.full((2, 3), np.nan),
        imports=np.full(3, np.nan),
        exports=np.full(3, np.nan),
        pop_needs=np.full(3, np.nan),
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
    state = replace(consumption_state, workforce_ratio=workforce_ratio)
    packages = needs_economy.calculate_buy_packages(state) if supply_packages else None
    scales = (
        needs_economy.calculate_pop_consumption_scales(state) if supply_scales else None
    )
    expenses = needs_economy.calculate_pop_expenses(
        state, buy_packages=packages, consumption_scales=scales
    )
    needs = needs_economy.calculate_pop_needs(
        state, buy_packages=packages, consumption_scales=scales
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
    packages = needs_economy.calculate_buy_packages(state).iloc[::-1, ::-1]
    scales = needs_economy.calculate_pop_consumption_scales(state)
    source_packages = packages.copy(deep=True)
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
        for key, value in vars(state).items()
        if isinstance(value, np.ndarray)
    }
    result = needs_economy.calculate_pop_expenses(
        state, buy_packages=packages, consumption_scales=scales
    )
    np.testing.assert_allclose(result, [[125, 5], [150, 5]])
    for key, value in source_arrays.items():
        np.testing.assert_array_equal(getattr(state, key), value)
        assert not np.shares_memory(result, getattr(state, key))
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
    pd.testing.assert_frame_equal(packages, source_packages)
    assert not np.shares_memory(result, scales)
    assert not np.shares_memory(result, packages.to_numpy())
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_expenses(
            state, buy_packages=packages, consumption_scales=scales
        ),
        [[125, 5], [150, 5]],
    )


def test_pop_consumption_reuse_after_wealth_and_price_changes(
    needs_economy: Economy, consumption_state: EconomyState
):
    packages = needs_economy.calculate_buy_packages(consumption_state)
    scales = needs_economy.calculate_pop_consumption_scales(consumption_state)
    changed = replace(consumption_state, pop_wealth=np.full((2, 2), 2))
    expected = scales * 500
    np.testing.assert_allclose(
        needs_economy.calculate_pop_expenses(
            changed, buy_packages=packages, consumption_scales=scales
        ),
        expected,
    )
    zero_prices = replace(changed, market_prices=np.zeros(3))
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_expenses(
            zero_prices, buy_packages=packages, consumption_scales=scales
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
    state = replace(consumption_state, workforce_ratio=0.25)
    scales = np.array([[1.0, 2.0], [3.0, 4.0]])
    original = scales.copy()
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.assign(consumption_mult=[np.nan, -1]),
    )
    packages = needs_economy.calculate_buy_packages(state) if supply_packages else None
    result = getattr(model, method)(
        state, buy_packages=packages, consumption_scales=scales
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
            replace(consumption_state, **{field: np.zeros(1)})
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
        state = replace(state, pops=np.full((2, 2), value))
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
    state = replace(needs_economy.solve(np.array([1.0, 0.0])), market_prices=prices)
    with pytest.raises(ValueError, match="state.market_prices"):
        needs_economy.calculate_pop_expenses(state)


@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_pop_consumption_empty_and_zero_scales(needs_economy: Economy, method: str):
    state = needs_economy.solve(np.zeros(2))
    expected_shape = (3,) if method == "calculate_pop_needs" else (2, 2)
    empty_packages = pd.DataFrame(columns=list(needs_economy.goods_index))
    for packages in (None, empty_packages):
        np.testing.assert_array_equal(
            getattr(needs_economy, method)(state, buy_packages=packages),
            np.zeros(expected_shape),
        )
    occupied = replace(state, pops=np.ones((2, 2)))
    with pytest.raises(ValueError, match="pop_wealth tiers.*buy_packages"):
        getattr(needs_economy, method)(
            occupied,
            buy_packages=empty_packages,
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
            model.calculate_pop_consumption_scales(replace(state, pops=state.pops * 2))
    elif case == "cost":
        with pytest.raises(ValueError, match="calculated basket costs"):
            needs_economy.calculate_pop_expenses(
                replace(state, market_prices=np.full(3, 1e308))
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
    packages = needs_economy.calculate_buy_packages(state).loc[[1]]
    scales = needs_economy.calculate_pop_consumption_scales(state)
    changed = replace(
        state,
        building_goods_flow=np.full((1, 1), np.nan),
        imports=np.full(1, np.nan),
        exports=np.full(1, np.nan),
        pop_needs=np.full(1, np.nan),
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
            changed, buy_packages=packages, consumption_scales=scales
        ),
        [[200, 0], [0, 0]],
    )


def test_calculate_pop_needs_exact_values_and_snapshot(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    original = {
        name: value.copy()
        for name, value in vars(state).items()
        if isinstance(value, np.ndarray)
    }
    result = needs_economy.calculate_pop_needs(state)
    np.testing.assert_allclose(result, [0.0, 5.0, 2.5])
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    assert not np.shares_memory(result, state.pop_needs)
    assert result @ needs_economy.base_prices == pytest.approx(200.0)
    for name, value in original.items():
        np.testing.assert_array_equal(getattr(state, name), value)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state), [0.0, 5.0, 2.5]
    )


def test_calculate_buy_packages_values_schema_and_snapshot(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    arrays = {
        name: value.copy()
        for name, value in vars(state).items()
        if isinstance(value, np.ndarray)
    }
    source_packages = needs_economy.df_buy_packages.copy(deep=True)
    source_needs = needs_economy.df_pop_needs.copy(deep=True)
    expected = pd.DataFrame(
        [[0.0, 5.0, 2.5], [0.0, 10.0, 5.0]],
        index=pd.Index([1, 2], dtype=np.int64, name="wealth"),
        columns=["unused", "a", "b"],
    )
    result = needs_economy.calculate_buy_packages(state)
    pd.testing.assert_frame_equal(result, expected)
    np.testing.assert_allclose(
        result.to_numpy() @ needs_economy.base_prices,
        source_packages.sort_values("wealth")["popneed_food"].to_numpy(),
    )
    for name, value in arrays.items():
        np.testing.assert_array_equal(getattr(state, name), value)
    pd.testing.assert_frame_equal(needs_economy.df_buy_packages, source_packages)
    pd.testing.assert_frame_equal(needs_economy.df_pop_needs, source_needs)
    result.iloc[:, :] = 999.0
    result.index = pd.Index([100, 200], name="wealth")
    result.columns = ["changed", "names", "here"]
    pd.testing.assert_frame_equal(needs_economy.calculate_buy_packages(state), expected)


def test_calculate_buy_packages_population_and_profession_independence(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    expected = needs_economy.calculate_buy_packages(state)
    changed = replace(
        state,
        pops=np.zeros((2, 2)),
        pop_wealth=np.full((2, 2), 999, dtype=np.int64),
        market_prices=state.market_prices * 100,
        pop_needs=np.full(3, 999.0),
    )
    pd.testing.assert_frame_equal(
        needs_economy.calculate_buy_packages(changed), expected
    )
    for professions in (
        needs_economy.df_pop_types.assign(consumption_mult=[-1.0, 100.0]),
        needs_economy.df_pop_types.drop(columns="consumption_mult"),
    ):
        model = replace(needs_economy, df_pop_types=professions)
        pd.testing.assert_frame_equal(model.calculate_buy_packages(changed), expected)


def test_calculate_buy_packages_aggregate_demand_consistency(needs_economy: Economy):
    state = replace(
        needs_economy.solve(np.array([1.0, 1.0])),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
        pop_wealth=np.array([[1, 2], [2, 1]]),
    )
    packages = needs_economy.calculate_buy_packages(state)
    # Wealth 1: 5,000 workers + 4,000 peasants * 0.05; wealth 2: 3,000 + 2,000 * 0.05.
    expected = packages.loc[1].to_numpy() * 0.52 + packages.loc[2].to_numpy() * 0.31
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(state), expected)
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, buy_packages=packages), expected
    )


def test_calculate_pop_needs_custom_packages_scaling_and_snapshot(
    needs_economy: Economy,
):
    state = replace(
        needs_economy.solve(np.array([1.0, 1.0])),
        pops=np.array([[5000.0, 2000.0], [3000.0, 4000.0]]),
        pop_wealth=np.array([[1, 2], [2, 1]]),
    )
    packages = pd.DataFrame(
        [[30, 10, 20], [3, 1, 2]],
        index=pd.Index([2.0, 1.0], name="custom"),
        columns=["b", "unused", "a"],
    )
    original = packages.copy(deep=True)
    arrays = {
        name: value.copy()
        for name, value in vars(state).items()
        if isinstance(value, np.ndarray)
    }
    expected = np.array([1, 2, 3]) * 0.52 + np.array([10, 20, 30]) * 0.31
    result = needs_economy.calculate_pop_needs(state, buy_packages=packages)
    np.testing.assert_allclose(result, expected)
    assert result.dtype == np.float64
    assert result.flags.owndata and result.flags.writeable
    assert not np.shares_memory(result, packages.to_numpy())
    for name, value in arrays.items():
        np.testing.assert_array_equal(getattr(state, name), value)
    pd.testing.assert_frame_equal(packages, original)
    result[:] = 999
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, buy_packages=packages), expected
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(
            replace(state, pops=2 * state.pops), buy_packages=packages
        ),
        2 * expected,
    )
    model = replace(
        needs_economy,
        df_pop_types=needs_economy.df_pop_types.drop(columns="consumption_mult"),
    )
    np.testing.assert_allclose(
        model.calculate_pop_needs(state, buy_packages=packages),
        np.array([1, 2, 3]) * 0.9 + np.array([10, 20, 30]) * 0.5,
    )


def test_calculate_pop_needs_supplied_packages_skip_unused_inputs(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_buy_packages(state)
    expected = needs_economy.calculate_pop_needs(state)
    changed = replace(
        state,
        building_goods_flow=np.array([[np.nan]]),
        imports=np.array([np.inf]),
        exports=np.array([np.nan]),
        market_prices=np.full(3, 999.0),
        pop_needs=np.full(3, 999.0),
    )
    model = replace(
        needs_economy,
        df_goods=needs_economy.df_goods.drop(columns="cost"),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
    )
    np.testing.assert_allclose(
        model.calculate_pop_needs(changed, buy_packages=packages), expected
    )


def test_calculate_pop_needs_supplied_packages_partial_and_empty(
    needs_economy: Economy,
):
    state = replace(
        needs_economy.solve(np.array([1.0, 0.0])),
        pop_wealth=np.array([[7, 0], [999, 0]]),
    )
    packages = pd.DataFrame([[1, 2, 3]], index=[7], columns=["unused", "a", "b"])
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state, buy_packages=packages), [1, 2, 3]
    )
    with pytest.raises(ValueError, match="pop_wealth tiers.*buy_packages"):
        needs_economy.calculate_pop_needs(
            replace(state, pop_wealth=np.full((2, 2), 8)), buy_packages=packages
        )
    empty = replace(state, pops=np.zeros((2, 2)))
    np.testing.assert_array_equal(
        needs_economy.calculate_pop_needs(empty, buy_packages=packages.iloc[:0]),
        np.zeros(3),
    )


@pytest.mark.parametrize(
    "index",
    [
        [1, 1],
        [0, 2],
        [-1, 2],
        [1.5, 2],
        [np.nan, 2],
        [np.inf, 2],
        [2**63, 2],
        ["1", "2"],
    ],
)
@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_calculate_pop_needs_supplied_packages_reject_invalid_wealth(
    needs_economy: Economy, index: list, method: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_buy_packages(state)
    packages.index = pd.Index(index)
    with pytest.raises(ValueError, match="buy_packages index"):
        getattr(needs_economy, method)(state, buy_packages=packages)


@pytest.mark.parametrize(
    "columns", [["unused", "a"], ["unused", "a", "b", "extra"], ["unused", "a", "a"]]
)
@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_calculate_pop_needs_supplied_packages_reject_invalid_columns(
    needs_economy: Economy, columns: list[str], method: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = pd.DataFrame(np.zeros((1, len(columns))), index=[1], columns=columns)
    with pytest.raises(ValueError, match="buy_packages.*columns"):
        getattr(needs_economy, method)(state, buy_packages=packages)


@pytest.mark.parametrize("value", [-1, np.nan, np.inf, "invalid"])
@pytest.mark.parametrize("method", ["calculate_pop_needs", "calculate_pop_expenses"])
def test_calculate_pop_needs_supplied_packages_reject_invalid_quantities(
    needs_economy: Economy, value: float | str, method: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    # Validate unused wealth rows too.
    packages = pd.DataFrame(
        {"unused": [0, 0], "a": [1, value], "b": [2, 3]}, index=[1, 2]
    )
    with pytest.raises(ValueError, match="buy_packages quantities"):
        getattr(needs_economy, method)(state, buy_packages=packages)


@pytest.mark.parametrize("field", ["pops", "pop_wealth"])
def test_calculate_pop_needs_supplied_packages_reject_misalignment(
    needs_economy: Economy, field: str
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_buy_packages(state)
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(
            replace(state, **{field: np.zeros(1)}), buy_packages=packages
        )


@pytest.mark.parametrize("field", ["pops", "consumption_mult"])
@pytest.mark.parametrize("value", [-1.0, np.nan, np.inf])
def test_calculate_pop_needs_supplied_packages_validate_population(
    needs_economy: Economy, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    packages = needs_economy.calculate_buy_packages(state)
    model = needs_economy
    if field == "pops":
        state = replace(state, pops=np.full((2, 2), value))
    else:
        model = replace(
            model,
            df_pop_types=model.df_pop_types.assign(consumption_mult=[value, 0.05]),
        )
    if field == "consumption_mult" and np.isnan(value):
        np.testing.assert_allclose(
            model.calculate_pop_needs(state, buy_packages=packages), [0, 5, 2.5]
        )
    else:
        with pytest.raises(ValueError, match=field):
            model.calculate_pop_needs(state, buy_packages=packages)


def test_calculate_pop_needs_professions_wealth_and_scaling(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 1.0]))
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(state), [0.0, 5.5, 2.75]
    )
    doubled = replace(state, pops=2 * state.pops)
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
    state = replace(
        model.solve(np.array([1.0, 0.0])),
        building_goods_flow=np.array([[0.0, *supply], [0.0, 0.0, 0.0]]),
    )
    np.testing.assert_allclose(model.calculate_pop_needs(state), [0.0, *expected])
    np.testing.assert_allclose(
        model.calculate_buy_packages(state).to_numpy(),
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
    changed = replace(state, **{field: value})
    expected = [0, 20 / 3, 5 / 3] if field == "imports" else [0, 10 / 3, 10 / 3]
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(changed), expected)
    np.testing.assert_allclose(
        needs_economy.calculate_buy_packages(changed).loc[1].to_numpy(), expected
    )
    if field != "imports":
        oversubscribed = replace(state, **{field: value * 3})
        if field == "building_goods_flow":
            flow = state.building_goods_flow.copy()
            flow[1] = [0.0, -300.0, 0.0]
            oversubscribed = replace(state, building_goods_flow=flow)
        np.testing.assert_allclose(
            needs_economy.calculate_pop_needs(oversubscribed), [0, 0, 5]
        )
        np.testing.assert_allclose(
            needs_economy.calculate_buy_packages(oversubscribed).loc[1].to_numpy(),
            [0, 0, 5],
        )


def test_calculate_pop_needs_ignores_prices_and_previous_demand(needs_economy: Economy):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    changed = replace(
        state, market_prices=100 * state.market_prices, pop_needs=np.full(3, 999.0)
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
    packages = model.calculate_buy_packages(state)
    np.testing.assert_allclose(packages.to_numpy(), [[0, 7, 2.5], [0, 14, 5]])
    np.testing.assert_allclose(packages.to_numpy() @ model.base_prices, [240, 480])


def test_calculate_pop_needs_zero_population_skips_wealth_lookup(
    needs_economy: Economy,
):
    state = needs_economy.solve(np.array([0.0, 0.0]))
    empty = replace(state, pop_wealth=np.zeros((2, 2), dtype=np.int64))
    np.testing.assert_array_equal(needs_economy.calculate_pop_needs(empty), np.zeros(3))
    partial = needs_economy.solve(np.array([1.0, 0.0]))
    partial = replace(partial, pop_wealth=np.array([[1, 0], [999, 0]]))
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(partial), [0, 5, 2.5])
    with pytest.raises(ValueError, match="pop_wealth tiers"):
        needs_economy.calculate_pop_needs(
            replace(partial, pop_wealth=np.full((2, 2), 3))
        )


@pytest.mark.parametrize(
    "field",
    [
        "pops",
        "pop_wealth",
        "building_goods_flow",
        "imports",
        "exports",
    ],
)
def test_calculate_pop_needs_rejects_misalignment(needs_economy: Economy, field: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(replace(state, **{field: np.zeros(1)}))
    if field not in {"pops", "pop_wealth"}:
        with pytest.raises(ValueError, match=field):
            needs_economy.calculate_buy_packages(replace(state, **{field: np.zeros(1)}))


@pytest.mark.parametrize(
    "field",
    ["pops", "imports", "exports"],
)
@pytest.mark.parametrize("value", [-1.0, np.nan, np.inf])
def test_calculate_pop_needs_rejects_invalid_quantities(
    needs_economy: Economy, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    bad = np.full(getattr(state, field).shape, value)
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(replace(state, **{field: bad}))
    if field != "pops":
        with pytest.raises(ValueError, match=field):
            needs_economy.calculate_buy_packages(replace(state, **{field: bad}))


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_calculate_pop_needs_rejects_nonfinite_flows(
    needs_economy: Economy, value: float
):
    state = replace(
        needs_economy.solve(np.array([1.0, 0.0])),
        building_goods_flow=np.full((2, 3), value),
    )
    with pytest.raises(ValueError, match="building_goods_flow"):
        needs_economy.calculate_pop_needs(state)
    with pytest.raises(ValueError, match="building_goods_flow"):
        needs_economy.calculate_buy_packages(state)


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
        model.calculate_buy_packages(model.solve(np.array([1.0, 0.0])))


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
            model.calculate_buy_packages(state)


def test_calculate_pop_needs_vanilla(economy: Economy):
    state = economy.solve(_first_producing_levels(economy))
    needs = economy.calculate_pop_needs(state)
    np.testing.assert_allclose(
        economy.calculate_pop_needs(
            state, buy_packages=economy.calculate_buy_packages(state)
        ),
        needs,
    )
    assert needs.shape == (len(economy.goods_index),)
    assert needs.dtype == np.float64
    assert np.isfinite(needs).all() and (needs >= 0).all() and (needs > 0).any()
    reordered = replace(economy, df_goods=economy.df_goods.iloc[::-1])
    fields = (
        "imports",
        "exports",
        "market_prices",
        "pop_needs",
    )
    reversed_state = replace(
        state,
        building_goods_flow=state.building_goods_flow[:, ::-1],
        **{name: getattr(state, name)[::-1] for name in fields},
    )
    np.testing.assert_allclose(
        reordered.calculate_pop_needs(reversed_state), needs[::-1]
    )


def test_pop_consumption_expenses_vanilla(economy: Economy):
    state = economy.solve(
        _first_producing_levels(economy), method="market", workforce_ratio=0.25
    )
    packages = economy.calculate_buy_packages(state)
    scales = economy.calculate_pop_consumption_scales(state)
    expenses = economy.calculate_pop_expenses(state)
    reused = economy.calculate_pop_expenses(
        state, buy_packages=packages, consumption_scales=scales
    )
    needs = economy.calculate_pop_needs(
        state, buy_packages=packages, consumption_scales=scales
    )
    assert expenses.shape == state.pops.shape == scales.shape
    assert expenses.dtype == scales.dtype == np.float64
    assert np.isfinite(expenses).all() and (expenses >= 0).all()
    assert (expenses > 0).any()
    np.testing.assert_allclose(expenses, reused)
    np.testing.assert_allclose(needs, economy.calculate_pop_needs(state))
    assert expenses.sum() == pytest.approx(needs @ state.market_prices)


def test_calculate_buy_packages_vanilla(economy: Economy):
    state = economy.solve(_first_producing_levels(economy))
    packages = economy.calculate_buy_packages(state)
    assert packages.index.name == "wealth"
    assert packages.index.dtype == np.int64
    np.testing.assert_array_equal(
        packages.index.to_numpy(), np.sort(economy.df_buy_packages["wealth"].to_numpy())
    )
    assert list(packages.columns) == list(economy.goods_index)
    assert packages.shape == (len(economy.df_buy_packages), len(economy.goods_index))
    values = packages.to_numpy()
    assert values.dtype == np.float64
    assert np.isfinite(values).all() and (values >= 0).all()
    np.testing.assert_allclose(
        values @ economy.base_prices,
        economy.df_buy_packages.sort_values("wealth")["total_popneeds"].to_numpy(),
    )
    reordered = replace(economy, df_goods=economy.df_goods.iloc[::-1])
    reversed_state = replace(
        state,
        building_goods_flow=state.building_goods_flow[:, ::-1],
        imports=state.imports[::-1],
        exports=state.exports[::-1],
    )
    pd.testing.assert_frame_equal(
        reordered.calculate_buy_packages(reversed_state), packages.iloc[:, ::-1]
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


def test_solve_imports_wrong_length(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    bad_imports = np.zeros(len(economy.goods_index) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="imports length"):
        economy.solve(levels, imports=bad_imports)


def test_solve_exports_wrong_length(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    bad_exports = np.zeros(len(economy.goods_index) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="exports length"):
        economy.solve(levels, exports=bad_exports)


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
    assert state.pop_balance.shape == (n_b, n_p)
    assert state.pop_needs.shape == (n_g,)
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


def test_solve_with_imports_exports(economy):
    n_g = len(economy.goods_index)
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    imports = np.full(n_g, 5.0, dtype=np.float64)
    exports = np.full(n_g, 3.0, dtype=np.float64)
    state = economy.solve(levels, imports=imports, exports=exports)
    np.testing.assert_array_equal(state.imports, imports)
    np.testing.assert_array_equal(state.exports, exports)
    np.testing.assert_allclose(state.sell_orders, state.building_goods_output + imports)
    np.testing.assert_allclose(state.buy_orders, state.building_goods_input + exports)


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
    imports = np.full(n_g, 0.5, dtype=np.float64)
    exports = np.full(n_g, 0.25, dtype=np.float64)
    pop_needs = np.full(n_g, 0.75, dtype=np.float64)
    throughput_multipliers = np.full(n_b, 2.0, dtype=np.float64)

    nominal = economy.solve(
        levels,
        imports=imports,
        exports=exports,
        throughput_multipliers=throughput_multipliers,
        pop_needs=pop_needs,
    )
    market = economy.solve(
        levels,
        method="market",
        imports=imports,
        exports=exports,
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
    np.testing.assert_allclose(market.pop_balance, nominal.pop_balance)
    np.testing.assert_allclose(market.pop_needs, nominal.pop_needs)
    np.testing.assert_allclose(
        market.market_prices,
        economy.market_prices(nominal.buy_orders, nominal.sell_orders),
    )


def test_solve_market_rejects_invalid_derived_orders(economy: Economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    invalid_imports = np.full(len(economy.goods_index), -1.0, dtype=np.float64)

    with pytest.raises(ValueError):
        economy.solve(levels, method="market", imports=invalid_imports)


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
    assert economy.construction_cost(state) == pytest.approx(expected)


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
    var = economy.market_prices_variance(state)
    assert var.shape == (len(economy.goods_index),)
    expected = (state.market_prices / economy.base_prices - 1) * 100
    np.testing.assert_allclose(var, expected)


def test_df_buildings(economy):
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    levels[0] = 3.0
    levels[1] = 1.0
    state = economy.solve(levels)
    df = economy.df_buildings(state)
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
    df = economy.df_market(state)
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


def test_wealth_per_capita():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    wealth = np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]])
    state = _make_state(pops=pops, pop_wealth=wealth)
    assert state.wealth_per_capita() == pytest.approx(35.0)


def test_wealth_per_capita_zero_population():
    state = _make_state()
    assert state.wealth_per_capita() == 0.0


def test_wealth_by_profession():
    pops = np.array([[4.0, 10.0, 0.0], [6.0, 20.0, 0.0]])
    wealth = np.array([[20.0, 40.0, 100.0], [20.0, 40.0, 100.0]])
    state = _make_state(pops=pops, pop_wealth=wealth)
    np.testing.assert_allclose(state.wealth_by_profession, np.array([20.0, 40.0, 0.0]))


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
    df = economy.df_pop(state)
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
        replace(state, workforce_ratio=ratio)
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
    households = replace(workers, workforce_ratio=0.25)
    assert households.dependents_per_worker == 3.0
    assert "dependents_per_worker" in vars(households)
    assert households.total_employment == workers.total_employment == 150.0
    assert households.total_population == 600.0
    assert households.gdp_per_capita() == workers.gdp_per_capita() / 4
    assert households.gdp_per_capita(annual=True) == workers.gdp_per_capita(True) / 4
    assert households.total_wealth == workers.total_wealth * 4
    assert households.average_wealth == workers.average_wealth
    assert households.wealth_per_capita() == workers.wealth_per_capita()
    assert households.wealth_distribution == workers.wealth_distribution
    assert households.gini_wealth == workers.gini_wealth
    np.testing.assert_array_equal(
        households.profession_shares, workers.profession_shares
    )
    np.testing.assert_array_equal(
        households.wealth_by_profession, workers.wealth_by_profession
    )
    assert replace(households).workforce_ratio == 0.25
    changed = replace(households, workforce_ratio=0.5)
    assert changed.dependents_per_worker == 1.0
    assert changed.total_population == 300.0
    assert households.dependents_per_worker == 3.0


def test_workforce_ratio_empty_population(income_economy: Economy):
    state = income_economy.solve(np.zeros(3), workforce_ratio=0.25)
    assert state.total_employment == state.total_population == 0
    assert state.gdp_per_capita() == state.wealth_per_capita() == 0
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
    np.testing.assert_array_equal(households.pop_balance, workers.pop_balance)
    np.testing.assert_array_equal(households.market_prices, workers.market_prices)
    packages = needs_economy.calculate_buy_packages(workers)
    pd.testing.assert_frame_equal(
        needs_economy.calculate_buy_packages(households), packages
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(households), [0, 0.125, 0.0625]
    )
    np.testing.assert_allclose(
        needs_economy.calculate_pop_needs(households, buy_packages=packages),
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
    np.testing.assert_array_equal(households.pop_balance, np.zeros((3, 3)))
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
    model.calculate_pop_income(replace(state, workforce_ratio=1.0))
    model.calculate_pop_income(model.solve(np.zeros(3), workforce_ratio=0.25))


def test_dependent_income_rejects_overflow(income_economy: Economy):
    pop_types = income_economy.df_pop_types.copy()
    pop_types["dependent_wage"] = [1e308, 0, 0]
    model = replace(income_economy, df_pop_types=pop_types)
    with pytest.raises(ValueError, match="calculated pop_income"):
        model.calculate_pop_income(model.solve(np.ones(3), workforce_ratio=0.25))
