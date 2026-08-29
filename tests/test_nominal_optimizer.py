import numpy as np
import pytest

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.nominal import NominalOptimizer


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


@pytest.fixture(scope="module")
def optimizer(economy: Economy) -> NominalOptimizer:
    return NominalOptimizer(economy)


def test_init_defaults(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    n_g = len(economy.goods_index())
    assert optimizer.model is economy
    assert optimizer.goods_matrix.shape == (n_b, n_g)
    assert optimizer.goods_matrix.dtype == np.float64
    assert optimizer.objective_vector.shape == (n_b,)
    assert optimizer.inequality_constraints == []
    assert optimizer.equality_constraints == []


def test_init_defensive_copy(economy: Economy):
    A = np.array([1.0, 2.0])
    b = np.array([3.0])
    ineq = [(A, b)]
    opt = NominalOptimizer(economy, inequality_constraints=ineq)
    assert len(opt.inequality_constraints) == 1
    ineq.append((A, b))
    assert len(opt.inequality_constraints) == 1


def test_init_invalid_objective(economy: Economy):
    with pytest.raises(ValueError, match="Unknown objective"):
        NominalOptimizer(economy, objective="bogus")


def test_gdp_vector(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    vec = optimizer.gdp_vector()
    assert vec.shape == (n_b,)
    np.testing.assert_allclose(vec, optimizer.goods_matrix @ economy.base_prices())


def test_base_prices(optimizer: NominalOptimizer, economy: Economy):
    np.testing.assert_array_equal(optimizer.base_prices(), economy.base_prices())


def test_employment_vector(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    vec = optimizer.employment_vector()
    assert vec.shape == (n_b,)
    expected = economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    np.testing.assert_array_equal(vec, expected)


def test_construction_cost_vector(optimizer: NominalOptimizer, economy: Economy):
    np.testing.assert_array_equal(
        optimizer.construction_cost_vector(), economy.construction_cost_vector()
    )


def test_goods_index(optimizer: NominalOptimizer, economy: Economy):
    assert optimizer.goods_index() == economy.goods_index()


def test_set_objective_gdp(optimizer: NominalOptimizer):
    r = optimizer.set_objective("gdp")
    assert r is optimizer
    np.testing.assert_array_equal(optimizer.objective_vector, -optimizer.gdp_vector())


def test_set_objective_employment(optimizer: NominalOptimizer):
    optimizer.set_objective("employment")
    np.testing.assert_array_equal(
        optimizer.objective_vector, -optimizer.employment_vector()
    )


def test_set_objective_automation(optimizer: NominalOptimizer):
    optimizer.set_objective("automation")
    np.testing.assert_array_equal(
        optimizer.objective_vector, optimizer.employment_vector()
    )


def test_set_objective_construction_cost(optimizer: NominalOptimizer):
    optimizer.set_objective("construction_cost")
    np.testing.assert_array_equal(
        optimizer.objective_vector, optimizer.construction_cost_vector()
    )


def test_set_objective_invalid(optimizer: NominalOptimizer):
    with pytest.raises(ValueError, match="Unknown objective"):
        optimizer.set_objective("bogus")


def test_reset(optimizer: NominalOptimizer, economy: Economy):
    optimizer.inequality_constraints.append((np.array([0.0]), np.array([0.0])))
    optimizer.goods_matrix = np.zeros_like(optimizer.goods_matrix)
    r = optimizer.reset("employment")
    assert r is optimizer
    assert optimizer.inequality_constraints == []
    assert optimizer.equality_constraints == []
    expected = economy.goods_output_matrix() - economy.goods_input_matrix()
    np.testing.assert_array_equal(optimizer.goods_matrix, expected)
    np.testing.assert_array_equal(
        optimizer.objective_vector, -optimizer.employment_vector()
    )


def test_add_throughput_bonus(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    bk = economy.df_production["building"].iloc[0]
    mask = (economy.df_production["building"] == bk).to_numpy()
    assert mask.sum() > 0
    gm_before = optimizer.goods_matrix.copy()
    emp_before = optimizer.employment_vector().copy()
    cc_before = optimizer.construction_cost_vector().copy()

    r = optimizer.add_throughput_bonus(bk, 2.0)
    assert r is optimizer
    np.testing.assert_allclose(optimizer.goods_matrix[mask], gm_before[mask] * 2)
    np.testing.assert_allclose(optimizer.goods_matrix[~mask], gm_before[~mask])
    np.testing.assert_array_equal(optimizer.employment_vector(), emp_before)
    np.testing.assert_array_equal(optimizer.construction_cost_vector(), cc_before)


def test_add_throughput_bonus_cumulative(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    bk = economy.df_production["building"].iloc[0]
    mask = (economy.df_production["building"] == bk).to_numpy()
    gm_orig = optimizer.goods_matrix.copy()
    optimizer.add_throughput_bonus(bk, 2.0).add_throughput_bonus(bk, 1.5)
    np.testing.assert_allclose(optimizer.goods_matrix[mask], gm_orig[mask] * 3.0)


def test_add_throughput_bonus_no_match(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    gm_before = optimizer.goods_matrix.copy()
    optimizer.add_throughput_bonus("building_does_not_exist", 2.0)
    np.testing.assert_array_equal(optimizer.goods_matrix, gm_before)


def test_constraint_limit_import(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    n_b, n_g = optimizer.goods_matrix.shape
    r = optimizer.constraint_limit_import(0.0)
    assert r is optimizer
    assert len(optimizer.inequality_constraints) == 1
    A, b = optimizer.inequality_constraints[-1]
    assert A.shape == (n_g, n_b)
    assert b.shape == (n_g,)
    np.testing.assert_allclose(A, -optimizer.goods_matrix.T)
    np.testing.assert_array_equal(b, np.zeros(n_g))


def test_constraint_limit_employment(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    r = optimizer.constraint_limit_employment(100.0)
    assert r is optimizer
    A, b = optimizer.inequality_constraints[-1]
    np.testing.assert_array_equal(A, optimizer.employment_vector())
    np.testing.assert_array_equal(b, np.array([100.0]))


def test_constraint_limit_construction_cost(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    r = optimizer.constraint_limit_construction_cost(5000.0)
    assert r is optimizer
    A, b = optimizer.inequality_constraints[-1]
    np.testing.assert_array_equal(A, optimizer.construction_cost_vector())
    np.testing.assert_array_equal(b, np.array([5000.0]))


def test_constraint_limit_building(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    n_b = len(economy.building_index())
    bk = economy.df_production["building"].iloc[0]
    mask = (economy.df_production["building"] == bk).to_numpy()
    r = optimizer.constraint_limit_building(bk, 10.0)
    assert r is optimizer
    A, b = optimizer.inequality_constraints[-1]
    assert A.shape == (n_b,)
    assert A.sum() == mask.sum()
    np.testing.assert_array_equal(b, np.array([10.0]))


def test_constraint_produce(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    gk = optimizer.goods_index()[0]
    r = optimizer.constraint_produce(gk, 5.0)
    assert r is optimizer
    A, b = optimizer.inequality_constraints[-1]
    np.testing.assert_array_equal(A, -optimizer.goods_matrix[:, 0])
    np.testing.assert_array_equal(b, np.array([-5.0]))


def test_constraint_produce_invalid(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    with pytest.raises(ValueError, match="not found in goods index"):
        optimizer.constraint_produce("not_a_real_good", 1.0)


def test_constraint_ban_building(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    n_b = len(economy.building_index())
    bk = economy.df_production["building"].iloc[0]
    r = optimizer.constraint_ban_building([bk])
    assert r is optimizer
    A, b = optimizer.equality_constraints[-1]
    assert A.shape == (n_b,)
    assert A.sum() >= 1
    np.testing.assert_array_equal(b, np.array([0.0]))


def test_constraint_ban_pm(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    n_b = len(economy.building_index())
    pm = economy.df_production["production_method"].iloc[0]
    pm_key = pm.split("+")[0]
    r = optimizer.constraint_ban_pm([pm_key])
    assert r is optimizer
    A, b = optimizer.equality_constraints[-1]
    assert A.shape == (n_b,)
    np.testing.assert_array_equal(b, np.array([0.0]))


def test_constraint_ban_pm_empty(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    r = optimizer.constraint_ban_pm([])
    assert r is optimizer
    A, b = optimizer.equality_constraints[-1]
    assert A.sum() == 0


def test_constraint_limit_era(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    optimizer.reset("gdp")
    era_threshold = int(economy.df_production["era"].median())  # pyright: ignore[reportArgumentType]
    r = optimizer.constraint_limit_era(era_threshold)
    assert r is optimizer
    A, b = optimizer.equality_constraints[-1]
    assert A.shape == (n_b,)
    expected = (economy.df_production["era"] > era_threshold).to_numpy().astype(float)
    np.testing.assert_array_equal(A, expected)
    np.testing.assert_array_equal(b, np.array([0.0]))


def test_constraint_limit_era_all(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    optimizer.reset("gdp")
    min_era = int(economy.df_production["era"].min())  # pyright: ignore[reportArgumentType]
    optimizer.constraint_limit_era(min_era - 1)
    A, b = optimizer.equality_constraints[-1]
    assert A.sum() == n_b


def test_constraint_limit_era_none(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp")
    max_era = int(economy.df_production["era"].max())  # pyright: ignore[reportArgumentType]
    optimizer.constraint_limit_era(max_era)
    A, b = optimizer.equality_constraints[-1]
    assert A.sum() == 0


def test_constraint_ban_building_group(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    optimizer.reset("gdp")
    bg = economy.df_production["building_group"].iloc[0]
    r = optimizer.constraint_ban_building_group(bg)
    assert r is optimizer
    A, b = optimizer.equality_constraints[-1]
    assert A.shape == (n_b,)
    expected = (economy.df_production["building_group"] == bg).to_numpy().astype(float)
    np.testing.assert_array_equal(A, expected)
    np.testing.assert_array_equal(b, np.array([0.0]))
    assert A.sum() > 0


def test_constraint_ban_building_group_no_match(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    optimizer.constraint_ban_building_group("bg_does_not_exist")
    A, b = optimizer.equality_constraints[-1]
    assert A.sum() == 0


def test_linprog(optimizer: NominalOptimizer, economy: Economy):
    n_b = len(economy.building_index())
    state = (
        optimizer.reset("gdp")
        .constraint_limit_construction_cost(5000.0)
        .constraint_limit_import(0.0)
        .linprog()
    )
    assert isinstance(state, EconomyState)
    assert state.building_levels.shape == (n_b,)
    assert np.dot(state.building_levels, optimizer.construction_cost_vector()) <= 5000.0
    np.testing.assert_allclose(
        state.gdp_weekly, float(np.dot(state.building_levels, optimizer.gdp_vector()))
    )


def test_linprog_with_ban(optimizer: NominalOptimizer, economy: Economy):
    bk = economy.df_production["building"].iloc[0]
    state = (
        optimizer.reset("gdp")
        .constraint_limit_construction_cost(5000.0)
        .constraint_limit_import(0.0)
        .constraint_ban_building([bk])
        .linprog()
    )
    assert isinstance(state, EconomyState)


def test_linprog_construction_cost_min(optimizer: NominalOptimizer):
    state = optimizer.reset("construction_cost").linprog()
    assert isinstance(state, EconomyState)
    np.testing.assert_allclose(state.building_levels, 0.0)


def test_linprog_with_throughput_bonus(optimizer: NominalOptimizer, economy: Economy):
    bk = economy.df_production["building"].iloc[0]
    state = (
        optimizer.reset("gdp")
        .add_throughput_bonus(bk, 2.0)
        .set_objective("gdp")
        .constraint_limit_construction_cost(5000.0)
        .constraint_limit_import(0.0)
        .linprog()
    )
    assert isinstance(state, EconomyState)
    np.testing.assert_allclose(
        state.gdp_weekly, float(np.dot(state.building_levels, optimizer.gdp_vector()))
    )


def test_import_marginals_before_solve(optimizer: NominalOptimizer):
    optimizer.reset("gdp")
    assert optimizer.import_marginals() is None


def test_import_marginals_after_solve(optimizer: NominalOptimizer, economy: Economy):
    n_goods = len(economy.goods_index())
    optimizer.reset("gdp").constraint_limit_construction_cost(
        5000.0
    ).constraint_limit_import(0.0)
    optimizer.linprog()
    marginals = optimizer.import_marginals()
    assert marginals is not None
    assert marginals.shape == (n_goods,)


def test_import_marginals_no_autarky(optimizer: NominalOptimizer, economy: Economy):
    optimizer.reset("gdp").constraint_limit_construction_cost(5000.0)
    optimizer.linprog()
    assert optimizer.import_marginals() is None
