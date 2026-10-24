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
    building_goods_input=None,
    building_goods_output=None,
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
        building_goods_input=building_goods_input
        if building_goods_input is not None
        else z,
        building_goods_output=building_goods_output
        if building_goods_output is not None
        else z,
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
    source = np.arange(3, dtype=np.float64)
    state = _make_state(building_goods_output=source)

    source[0] = 999.0

    assert state.building_goods_output[0] == 0.0
    for name in (
        "building_levels",
        "building_goods_input",
        "building_goods_output",
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
        building_goods_output=np.array([10.0, 0.0, 5.0]),
        imports=np.array([2.0, 1.0, 0.0]),
    )
    np.testing.assert_array_equal(state.sell_orders, np.array([12.0, 1.0, 5.0]))


def test_buy_orders():
    state = _make_state(
        building_goods_input=np.array([3.0, 0.0, 1.0]),
        exports=np.array([0.0, 2.0, 1.0]),
        pop_needs=np.array([1.0, 1.0, 1.0]),
    )
    np.testing.assert_array_equal(state.buy_orders, np.array([4.0, 3.0, 3.0]))


def test_gdp_weekly():
    state = _make_state(
        building_goods_input=np.array([1.0, 2.0, 1.0]),
        building_goods_output=np.array([5.0, 0.0, 3.0]),
        market_prices=np.array([2.0, 1.0, 4.0]),
    )
    # net = [4, -2, 2]; net * prices = [8, -2, 8]; sum = 14
    assert state.gdp_weekly == pytest.approx(14.0)


def test_gdp_weekly_and_annual():
    state = _make_state(
        building_goods_input=np.array([1.0, 2.0, 1.0]),
        building_goods_output=np.array([5.0, 0.0, 3.0]),
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
        building_goods_output=np.array([0.0, *supply]),
    )
    np.testing.assert_allclose(model.calculate_pop_needs(state), [0.0, *expected])


@pytest.mark.parametrize("field", ["imports", "building_goods_input", "exports"])
def test_calculate_pop_needs_nonpop_market_orders(needs_economy: Economy, field: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    changed = replace(state, **{field: np.array([0.0, 100.0, 0.0])})
    expected = [0, 20 / 3, 5 / 3] if field == "imports" else [0, 10 / 3, 10 / 3]
    np.testing.assert_allclose(needs_economy.calculate_pop_needs(changed), expected)
    if field != "imports":
        oversubscribed = replace(state, **{field: np.array([0.0, 300.0, 0.0])})
        np.testing.assert_allclose(
            needs_economy.calculate_pop_needs(oversubscribed), [0, 0, 5]
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
        "building_goods_input",
        "building_goods_output",
        "imports",
        "exports",
    ],
)
def test_calculate_pop_needs_rejects_misalignment(needs_economy: Economy, field: str):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(replace(state, **{field: np.zeros(1)}))


@pytest.mark.parametrize(
    "field",
    ["pops", "building_goods_input", "building_goods_output", "imports", "exports"],
)
@pytest.mark.parametrize("value", [-1.0, np.nan, np.inf])
def test_calculate_pop_needs_rejects_invalid_quantities(
    needs_economy: Economy, field: str, value: float
):
    state = needs_economy.solve(np.array([1.0, 0.0]))
    bad = np.full(getattr(state, field).shape, value)
    with pytest.raises(ValueError, match=field):
        needs_economy.calculate_pop_needs(replace(state, **{field: bad}))


@pytest.mark.parametrize("value", [0.0, -1.0, np.nan, np.inf])
def test_calculate_pop_needs_rejects_invalid_base_prices(
    needs_economy: Economy, value: float
):
    model = replace(
        needs_economy, df_goods=needs_economy.df_goods.assign(cost=[10, value, 40])
    )
    with pytest.raises(ValueError, match="base_prices"):
        model.calculate_pop_needs(model.solve(np.array([1.0, 0.0])))


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


def test_calculate_pop_needs_vanilla(economy: Economy):
    state = economy.solve(_first_producing_levels(economy))
    needs = economy.calculate_pop_needs(state)
    assert needs.shape == (len(economy.goods_index),)
    assert needs.dtype == np.float64
    assert np.isfinite(needs).all() and (needs >= 0).all() and (needs > 0).any()
    reordered = replace(economy, df_goods=economy.df_goods.iloc[::-1])
    fields = (
        "building_goods_input",
        "building_goods_output",
        "imports",
        "exports",
        "market_prices",
        "pop_needs",
    )
    reversed_state = replace(
        state, **{name: getattr(state, name)[::-1] for name in fields}
    )
    np.testing.assert_allclose(
        reordered.calculate_pop_needs(reversed_state), needs[::-1]
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
