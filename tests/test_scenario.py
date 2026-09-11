import numpy as np
import pandas as pd
import pytest

from vic3_analysis import state_region_resource_limits
from vic3_analysis.analysis.economy import Economy
from vic3_analysis.optimize.scenario import Scenario

TERMINAL_GOOD = "automobiles"


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


def test_defaults():
    scenario = Scenario()
    assert scenario.produce == ()
    assert scenario.objective == "automation"
    assert scenario.import_limit == 0.0
    assert scenario.banned_pms == ()
    assert scenario.building_limits == ()
    assert scenario.banned_building_groups == ()
    assert scenario.throughput_bonuses == ()
    assert scenario.era_cap is None
    assert scenario.construction_cost_cap is None
    assert scenario.employment_cap is None
    assert scenario.arable_land_cap is None
    assert scenario.min_infrastructure is None
    assert scenario.urbanization_per_center is None
    assert scenario.imports == ()
    assert scenario.exports == ()
    assert scenario.pop_needs == ()
    assert scenario.name is None


def test_invalid_objective_raises_at_construction():
    with pytest.raises(ValueError, match="Unknown objective"):
        Scenario(objective="bogus")


def test_gdp_per_capita_is_a_market_only_objective(economy: Economy):
    scenario = Scenario(objective="gdp_per_capita")
    with pytest.raises(ValueError, match="MarketOptimizer"):
        scenario.objective_vector(economy)


def test_frozen():
    scenario = Scenario(produce=(("steel", 1.0),))
    attribute = "objective"
    with pytest.raises(Exception):
        setattr(scenario, attribute, "gdp")


def test_display_name():
    assert Scenario(name="recipe-a").display_name() == "recipe-a"
    assert Scenario(produce=(("steel", 5.0),)).display_name() == "steel"
    assert (
        Scenario(produce=(("steel", 5.0), ("tools", 2.0))).display_name()
        == "steel+tools"
    )
    assert Scenario().display_name() == "unnamed"


def test_goods_matrices_without_bonuses(economy: Economy):
    scenario = Scenario()
    np.testing.assert_allclose(
        scenario.goods_input_matrix(economy), economy.goods_input_matrix()
    )
    np.testing.assert_allclose(
        scenario.goods_output_matrix(economy), economy.goods_output_matrix()
    )
    np.testing.assert_allclose(
        scenario.goods_matrix(economy),
        economy.goods_output_matrix() - economy.goods_input_matrix(),
    )


def test_goods_matrices_with_throughput_bonus(economy: Economy):
    building_key = "building_automotive_industry"
    scenario = Scenario(throughput_bonuses=((building_key, 2.0),))
    mask = (economy.df_production["building"] == building_key).to_numpy()
    base_out = economy.goods_output_matrix()
    base_in = economy.goods_input_matrix()
    out = scenario.goods_output_matrix(economy)
    ins = scenario.goods_input_matrix(economy)
    np.testing.assert_allclose(out[mask], base_out[mask] * 2.0)
    np.testing.assert_allclose(ins[mask], base_in[mask] * 2.0)
    np.testing.assert_allclose(out[~mask], base_out[~mask])
    np.testing.assert_allclose(ins[~mask], base_in[~mask])
    # employment and construction cost are unaffected by bonuses.
    np.testing.assert_array_equal(
        economy.employment_vector(), economy.employment_vector()
    )


def test_throughput_bonuses_cumulative(economy: Economy):
    building_key = str(economy.df_production["building"].iloc[0])
    scenario = Scenario(throughput_bonuses=((building_key, 2.0), (building_key, 1.5)))
    mask = (economy.df_production["building"] == building_key).to_numpy()
    base = economy.goods_output_matrix()
    out = scenario.goods_output_matrix(economy)
    np.testing.assert_allclose(out[mask], base[mask] * 3.0)
    np.testing.assert_allclose(out[~mask], base[~mask])


def test_throughput_bonuses_no_match(economy: Economy):
    scenario = Scenario(throughput_bonuses=(("building_does_not_exist", 2.0),))
    np.testing.assert_allclose(
        scenario.goods_output_matrix(economy), economy.goods_output_matrix()
    )


def test_gdp_vector(economy: Economy):
    scenario = Scenario()
    np.testing.assert_allclose(
        scenario.gdp_vector(economy),
        scenario.goods_matrix(economy) @ economy.base_prices(),
    )


def test_gdp_vector_reflects_bonuses(economy: Economy):
    building_key = str(economy.df_production["building"].iloc[0])
    scenario = Scenario(throughput_bonuses=((building_key, 2.0),))
    base = Scenario()
    assert not np.allclose(scenario.gdp_vector(economy), base.gdp_vector(economy))


def test_objective_vector_signs(economy: Economy):
    for objective in ("gdp", "employment", "automation", "construction_cost"):
        scenario = Scenario(objective=objective)
        vec = scenario.objective_vector(economy)
        if objective == "gdp":
            np.testing.assert_allclose(vec, -scenario.gdp_vector(economy))
        elif objective == "employment":
            np.testing.assert_allclose(vec, -economy.employment_vector())
        elif objective == "automation":
            np.testing.assert_allclose(vec, economy.employment_vector())
        else:
            np.testing.assert_array_equal(vec, economy.construction_cost_vector())


def test_inequality_constraints_order_and_content(economy: Economy):
    scenario = Scenario(
        produce=(("automobiles", 1.0), ("steel", 2.0)),
        construction_cost_cap=5000.0,
        employment_cap=1000.0,
        building_limits=(("building_dye_plantation", 0.0),),
        arable_land_cap=25.0,
        min_infrastructure=5.0,
    )
    A_ub, b_ub = scenario.inequality_constraints(economy)
    assert A_ub is not None
    assert b_ub is not None
    n_b = len(economy.building_index())
    n_goods = len(economy.goods_index())
    goods_index = economy.goods_index()
    # import (n_goods) + cost (1) + employment (1) + produce (2) + limits (1)
    # + arable land (1) + infra (1).
    assert A_ub.shape == (n_goods + 7, n_b)
    assert b_ub.shape == (n_goods + 7,)
    assert A_ub.dtype == np.float64
    assert b_ub.dtype == np.float64

    # import block leads.
    np.testing.assert_allclose(A_ub[:n_goods], -scenario.goods_matrix(economy).T)
    np.testing.assert_array_equal(b_ub[:n_goods], np.zeros(n_goods))

    offset = n_goods
    np.testing.assert_array_equal(A_ub[offset], economy.construction_cost_vector())
    assert b_ub[offset] == 5000.0
    offset += 1
    np.testing.assert_array_equal(A_ub[offset], economy.employment_vector())
    assert b_ub[offset] == 1000.0
    offset += 1
    np.testing.assert_allclose(
        A_ub[offset],
        -scenario.goods_matrix(economy)[:, goods_index.index("automobiles")],
    )
    np.testing.assert_allclose(
        A_ub[offset + 1],
        -scenario.goods_matrix(economy)[:, goods_index.index("steel")],
    )
    np.testing.assert_array_equal(b_ub[offset : offset + 2], np.array([-1.0, -2.0]))
    offset += 2
    mask = (economy.df_production["building"] == "building_dye_plantation").to_numpy()
    np.testing.assert_array_equal(A_ub[offset], mask.astype(np.float64))
    assert b_ub[offset] == 0.0
    offset += 1
    np.testing.assert_array_equal(A_ub[offset], economy.arable_land_vector())
    assert b_ub[offset] == 25.0
    offset += 1
    infrastructure = (
        economy.df_production["infrastructure_usage_per_level"]
        .fillna(0)
        .to_numpy(dtype=np.float64)
    )
    np.testing.assert_array_equal(A_ub[offset], -infrastructure)
    assert b_ub[offset] == -5.0


def test_state_region_limits_compose_with_building_limit_constraints(
    economy: Economy,
):
    state_regions = pd.DataFrame(
        {
            "key": ["STATE_TEST"],
            "resource_building_coal_mine": [2],
            "resource_building_iron_mine": [3],
        }
    )
    limits = state_region_resource_limits(state_regions, ["STATE_TEST"])
    scenario = Scenario(
        import_limit=None,
        objective="construction_cost",
        building_limits=tuple(limits.items()),
    )

    A_ub, b_ub = scenario.inequality_constraints(economy)

    assert A_ub is not None
    assert b_ub is not None
    buildings = economy.df_production["building"].to_numpy()
    np.testing.assert_array_equal(
        A_ub[0], (buildings == "building_coal_mine").astype(np.float64)
    )
    np.testing.assert_array_equal(
        A_ub[1], (buildings == "building_iron_mine").astype(np.float64)
    )
    np.testing.assert_array_equal(b_ub, np.array([2.0, 3.0]))
    manufacturing = economy.df_production["building_group"].eq("bg_manufacturing")
    assert not A_ub[:, manufacturing.to_numpy()].any()


def test_inequality_constraints_none_when_absent(economy: Economy):
    scenario = Scenario(import_limit=None, objective="construction_cost")
    A_ub, b_ub = scenario.inequality_constraints(economy)
    assert A_ub is None
    assert b_ub is None


def test_import_limit_variants(economy: Economy):
    n_goods = len(economy.goods_index())
    n_b = len(economy.building_index())
    # None disables the import constraint entirely (produce row only).
    scenario = Scenario(import_limit=None, produce=(("automobiles", 1.0),))
    A_ub, b_ub = scenario.inequality_constraints(economy)
    assert A_ub is not None
    assert b_ub is not None
    assert A_ub.shape == (1, n_b)
    assert b_ub.shape == (1,)
    # Nonzero limits generalise autarky.
    scenario = Scenario(import_limit=5.0)
    A_ub, b_ub = scenario.inequality_constraints(economy)
    assert A_ub is not None
    assert b_ub is not None
    assert A_ub.shape == (n_goods, n_b)
    np.testing.assert_array_equal(b_ub, np.full(n_goods, 5.0))


def test_default_scenario_constraints(economy: Economy):
    scenario = Scenario()
    A_ub, b_ub = scenario.inequality_constraints(economy)
    assert A_ub is not None
    assert b_ub is not None
    # the autarky import cap only
    assert A_ub.shape == (len(economy.goods_index()), len(economy.building_index()))
    assert b_ub.shape == (len(economy.goods_index()),)
    A_eq, b_eq = scenario.equality_constraints(economy)
    assert A_eq is None
    assert b_eq is None


def test_produce_unknown_good(economy: Economy):
    with pytest.raises(ValueError, match="not found in goods index"):
        Scenario(produce=(("not_a_real_good", 1.0),)).inequality_constraints(economy)


def test_market_context_vectors_sum_duplicate_goods(economy: Economy):
    scenario = Scenario(
        imports=(("tools", 2.0), ("tools", 3.0)),
        exports=(("coal", 4.0),),
        pop_needs=(("grain", 5.0),),
    )
    goods = economy.goods_index()
    imports = scenario.imports_vector(economy)
    exports = scenario.exports_vector(economy)
    pop_needs = scenario.pop_needs_vector(economy)
    assert imports[goods.index("tools")] == pytest.approx(5.0)
    assert exports[goods.index("coal")] == pytest.approx(4.0)
    assert pop_needs[goods.index("grain")] == pytest.approx(5.0)


def test_market_context_vectors_reject_invalid_entries(economy: Economy):
    invalid_good = (
        Scenario(imports=(("not_a_real_good", 1.0),)),
        Scenario(exports=(("not_a_real_good", 1.0),)),
        Scenario(pop_needs=(("not_a_real_good", 1.0),)),
    )
    invalid_amount = (
        Scenario(imports=(("tools", -1.0),)),
        Scenario(exports=(("tools", -1.0),)),
        Scenario(pop_needs=(("tools", -1.0),)),
    )
    vector_methods = ("imports_vector", "exports_vector", "pop_needs_vector")
    for scenario, method_name in zip(invalid_good, vector_methods, strict=True):
        with pytest.raises(ValueError, match="not found in goods index"):
            getattr(scenario, method_name)(economy)
    for scenario, method_name in zip(invalid_amount, vector_methods, strict=True):
        with pytest.raises(ValueError, match="finite non-negative"):
            getattr(scenario, method_name)(economy)


def test_equality_constraints_order_and_content(economy: Economy):
    median = economy.df_production["era"].median()
    assert isinstance(median, float)
    era_threshold = int(median)
    building_group = str(economy.df_production["building_group"].iloc[0])
    pm_key = str(economy.df_production["production_method"].iloc[0]).split("+")[0]
    scenario = Scenario(
        era_cap=era_threshold,
        banned_pms=(pm_key,),
        banned_building_groups=(building_group,),
        urbanization_per_center=100.0,
    )
    A_eq, b_eq = scenario.equality_constraints(economy)
    assert A_eq is not None
    assert b_eq is not None
    n_b = len(economy.building_index())
    assert A_eq.shape == (4, n_b)
    assert b_eq.shape == (4,)
    np.testing.assert_array_equal(b_eq, np.zeros(4))

    expected_era = (economy.df_production["era"] > era_threshold).to_numpy()
    np.testing.assert_array_equal(A_eq[0], expected_era.astype(np.float64))

    assert A_eq[1].sum() >= 1

    expected_group = (
        economy.df_production["building_group"] == building_group
    ).to_numpy()
    np.testing.assert_array_equal(A_eq[2], expected_group.astype(np.float64))

    urbanization = (
        economy.df_production["urbanization"].fillna(0).to_numpy(dtype=np.float64)
    )
    urban_center = (
        economy.df_production["building"] == "building_urban_center"
    ).to_numpy()
    assert urban_center.sum() > 0
    np.testing.assert_allclose(A_eq[3], urbanization - 100.0 * urban_center)


def test_equality_constraints_none_when_absent(economy: Economy):
    A_eq, b_eq = Scenario().equality_constraints(economy)
    assert A_eq is None
    assert b_eq is None


def test_linprog_args(economy: Economy):
    scenario = Scenario(
        produce=(("automobiles", 1.0),),
        objective="construction_cost",
        era_cap=1,
    )
    args = scenario.linprog_args(economy)
    assert set(args) == {"c", "A_ub", "b_ub", "A_eq", "b_eq"}
    np.testing.assert_array_equal(args["c"], scenario.objective_vector(economy))
    A_ub, b_ub = scenario.inequality_constraints(economy)
    A_eq, b_eq = scenario.equality_constraints(economy)
    np.testing.assert_array_equal(args["A_ub"], A_ub)
    np.testing.assert_array_equal(args["b_ub"], b_ub)
    np.testing.assert_array_equal(args["A_eq"], A_eq)
    np.testing.assert_array_equal(args["b_eq"], b_eq)
    assert args["A_ub"] is not None
    assert args["b_ub"] is not None
    assert args["A_eq"] is not None
    assert args["b_eq"] is not None
    assert args["A_ub"].shape[0] == args["b_ub"].shape[0]
    assert args["A_eq"].shape[0] == args["b_eq"].shape[0]


def test_linprog_args_empty_constraints(economy: Economy):
    scenario = Scenario(objective="construction_cost", import_limit=None)
    args = scenario.linprog_args(economy)
    assert args["A_ub"] is None
    assert args["b_ub"] is None
    assert args["A_eq"] is None
    assert args["b_eq"] is None
    assert args["c"].shape == (len(economy.building_index()),)


def test_import_marginals_requires_import_and_result(economy: Economy):
    assert Scenario().import_marginals(economy, None) is None
    assert Scenario(import_limit=None).import_marginals(economy, None) is None
