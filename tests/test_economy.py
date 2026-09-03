import numpy as np
import pandas as pd
import pytest

from vic3_analysis.analysis.economy import Economy, EconomyState


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


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


def _first_producing_levels(economy: Economy) -> np.ndarray:
    out = economy.goods_output_matrix()
    idx = int(np.argmax(out.sum(axis=1) > 0))
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
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
    assert eco2.df_production is economy.df_production
    assert eco2.df_goods is economy.df_goods
    assert eco2.df_pop_types is economy.df_pop_types


def test_indices_consistent(economy):
    buildings = economy.building_index()
    goods_idx = economy.goods_index()
    pops = economy.pop_index()
    assert len(buildings) == len(economy.df_production)
    assert len(goods_idx) == len(economy.df_goods)
    assert len(pops) == len(economy.df_pop_types)
    assert all("+" in b for b in buildings)
    assert goods_idx == economy.df_goods["key"].tolist()
    assert pops == economy.df_pop_types["key"].tolist()


def test_base_prices(economy):
    prices = economy.base_prices()
    assert prices.shape == (len(economy.df_goods),)
    assert prices.dtype == np.float64
    np.testing.assert_array_equal(
        prices, economy.df_goods["cost"].to_numpy(dtype=np.float64)
    )


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


def test_employment_matrix(economy):
    mat = economy.employment_matrix()
    assert mat.shape == (len(economy.df_production), len(economy.df_pop_types))
    assert mat.dtype == np.float64


def test_pop_wealth_init(economy):
    w = economy.pop_wealth_init()
    assert w.shape == (len(economy.df_pop_types),)
    assert w.dtype == np.float64
    np.testing.assert_array_equal(
        w, economy.df_pop_types["start_quality_of_life"].to_numpy(dtype=np.float64)
    )


def test_construction_cost_vector(economy):
    cc = economy.construction_cost_vector()
    assert cc.shape == (len(economy.df_production),)
    assert cc.dtype == np.float64
    np.testing.assert_array_equal(
        cc, economy.df_production["construction_cost"].to_numpy(dtype=np.float64)
    )


def test_employment_vector(economy):
    emp = economy.employment_vector()
    assert emp.shape == (len(economy.df_production),)
    assert emp.dtype == np.float64
    expected = economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    np.testing.assert_array_equal(emp, expected)
    # equals the row sums of the employment matrix.
    np.testing.assert_allclose(emp, economy.employment_matrix().sum(axis=1))


def test_solve_invalid_method(economy):
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
    with pytest.raises(ValueError, match="Invalid method"):
        economy.solve(levels, method="bogus")


def test_solve_non_1d(economy):
    levels = np.zeros((len(economy.building_index()), 1), dtype=np.float64)
    with pytest.raises(ValueError, match="1-D"):
        economy.solve(levels)


def test_solve_wrong_length(economy):
    levels = np.zeros(len(economy.building_index()) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="length must match"):
        economy.solve(levels)


def test_solve_imports_wrong_length(economy):
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
    bad_imports = np.zeros(len(economy.goods_index()) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="imports length"):
        economy.solve(levels, imports=bad_imports)


def test_solve_exports_wrong_length(economy):
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
    bad_exports = np.zeros(len(economy.goods_index()) + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="exports length"):
        economy.solve(levels, exports=bad_exports)


def test_solve_nominal(economy):
    n_b = len(economy.building_index())
    n_g = len(economy.goods_index())
    n_p = len(economy.pop_index())
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
    np.testing.assert_array_equal(state.market_prices, economy.base_prices())
    np.testing.assert_allclose(
        state.pop_wealth,
        np.broadcast_to(economy.pop_wealth_init(), (n_b, n_p)),
    )
    assert np.all(state.imports == 0)
    assert np.all(state.exports == 0)
    assert np.all(state.pop_needs == 0)
    np.testing.assert_allclose(
        state.building_goods_input, levels @ economy.goods_input_matrix()
    )
    np.testing.assert_allclose(
        state.building_goods_output, levels @ economy.goods_output_matrix()
    )
    np.testing.assert_allclose(
        state.pops, levels[:, None] * economy.employment_matrix()
    )


def test_solve_with_imports_exports(economy):
    n_g = len(economy.goods_index())
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
    imports = np.full(n_g, 5.0, dtype=np.float64)
    exports = np.full(n_g, 3.0, dtype=np.float64)
    state = economy.solve(levels, imports=imports, exports=exports)
    np.testing.assert_array_equal(state.imports, imports)
    np.testing.assert_array_equal(state.exports, exports)
    np.testing.assert_allclose(state.sell_orders, state.building_goods_output + imports)
    np.testing.assert_allclose(state.buy_orders, state.building_goods_input + exports)


def test_construction_cost(economy):
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
    levels[0] = 2.0
    levels[1] = 1.0
    state = economy.solve(levels)
    expected = float(np.dot(levels, economy.construction_cost_vector()))
    assert economy.construction_cost(state) == pytest.approx(expected)


def test_market_prices_variance(economy):
    levels = _first_producing_levels(economy)
    state = economy.solve(levels)
    var = economy.market_prices_variance(state)
    assert var.shape == (len(economy.goods_index()),)
    expected = (state.market_prices / economy.base_prices() - 1) * 100
    np.testing.assert_allclose(var, expected)


def test_df_buildings(economy):
    levels = np.zeros(len(economy.building_index()), dtype=np.float64)
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
            "key": economy.building_index(),
            "level": levels,
            "construction_cost": economy.construction_cost_vector() * levels,
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
    assert set(df["profession"]) <= set(economy.pop_index())
    assert np.allclose(df["avg_wealth"], df["total_wealth"] / df["employment"])
