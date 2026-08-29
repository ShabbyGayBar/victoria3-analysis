import numpy as np
import pandas as pd
import pytest

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.analysis.supply_chain import (
    ProducerNode,
    Scenario,
    SupplyChainNode,
    bottleneck,
    compare_scenarios,
    upstream_tree,
    value_added_breakdown,
)

TERMINAL_GOOD = "automobiles"
RAW_GOOD = "services"


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


@pytest.fixture(scope="module")
def automation_scenario() -> Scenario:
    return Scenario(
        terminal_good=TERMINAL_GOOD,
        target_amount=1.0,
        objective="automation",
        autarky=True,
    )


@pytest.fixture(scope="module")
def solved(economy: Economy, automation_scenario: Scenario):
    optimizer = automation_scenario.build_optimizer(economy)
    state = optimizer.linprog()
    return optimizer, state


def test_scenario_defaults():
    scenario = Scenario(terminal_good="steel", target_amount=5.0)
    assert scenario.objective == "automation"
    assert scenario.autarky is True
    assert scenario.banned_pms == ()
    assert scenario.banned_buildings == ()
    assert scenario.throughput_bonuses == ()
    assert scenario.era_cap is None
    assert scenario.construction_cost_cap is None
    assert scenario.employment_cap is None
    assert scenario.name is None


def test_scenario_display_name():
    assert Scenario(terminal_good="steel", target_amount=1.0).display_name() == "steel"
    assert (
        Scenario(
            terminal_good="steel", target_amount=1.0, name="recipe-a"
        ).display_name()
        == "recipe-a"
    )


def test_scenario_frozen():
    scenario = Scenario(terminal_good="steel", target_amount=1.0)
    with pytest.raises(Exception):
        setattr(scenario, "terminal_good", "iron")


def test_build_optimizer_objective_sign(economy: Economy):
    good = TERMINAL_GOOD
    for objective in ("gdp", "employment", "automation", "construction_cost"):
        optimizer = Scenario(
            terminal_good=good, target_amount=1.0, objective=objective
        ).build_optimizer(economy)
        emp = optimizer.employment_vector()
        gdp = optimizer.gdp_vector()
        if objective == "gdp":
            np.testing.assert_allclose(optimizer.objective_vector, -gdp)
        elif objective == "employment":
            np.testing.assert_allclose(optimizer.objective_vector, -emp)
        elif objective == "automation":
            np.testing.assert_allclose(optimizer.objective_vector, emp)
        elif objective == "construction_cost":
            np.testing.assert_array_equal(
                optimizer.objective_vector, optimizer.construction_cost_vector()
            )


def test_build_optimizer_invalid_objective(economy: Economy):
    with pytest.raises(ValueError, match="Unknown objective"):
        Scenario(
            terminal_good=TERMINAL_GOOD, target_amount=1.0, objective="bogus"
        ).build_optimizer(economy)


def test_build_optimizer_unknown_good(economy: Economy):
    with pytest.raises(ValueError, match="not found in goods index"):
        Scenario(terminal_good="not_a_real_good", target_amount=1.0).build_optimizer(
            economy
        )


def test_build_optimizer_constraints(economy: Economy):
    n_goods = len(economy.goods_index())
    optimizer = Scenario(
        terminal_good=TERMINAL_GOOD,
        target_amount=1.0,
        banned_pms=("pm_diesel_engines",),
        banned_buildings=("building_dye_plantation",),
    ).build_optimizer(economy)
    # autarky -> one (A, b) pair with n_goods rows; produce -> one 1-row pair.
    assert len(optimizer.inequality_constraints) == 2
    a_import, _ = optimizer.inequality_constraints[0]
    assert a_import.shape == (n_goods, len(economy.building_index()))
    a_produce, b_produce = optimizer.inequality_constraints[1]
    assert a_produce.ndim == 1
    assert b_produce.shape == (1,)
    # banned pms + banned buildings -> two equality pairs.
    assert len(optimizer.equality_constraints) == 2


def test_build_optimizer_no_autarky(economy: Economy):
    optimizer = Scenario(
        terminal_good=TERMINAL_GOOD,
        target_amount=1.0,
        autarky=False,
    ).build_optimizer(economy)
    # only the produce constraint, no import caps.
    assert len(optimizer.inequality_constraints) == 1


def test_build_optimizer_era_and_caps(economy: Economy):
    optimizer = Scenario(
        terminal_good=TERMINAL_GOOD,
        target_amount=1.0,
        era_cap=1,
        construction_cost_cap=5000.0,
        employment_cap=1000.0,
    ).build_optimizer(economy)
    # autarky + construction cap + employment cap + produce = 4 inequality pairs.
    assert len(optimizer.inequality_constraints) == 4
    assert len(optimizer.equality_constraints) == 1


def test_build_optimizer_throughput_bonus(economy: Economy):
    bk = "building_automotive_industry"
    optimizer = Scenario(
        terminal_good=TERMINAL_GOOD,
        target_amount=1.0,
        throughput_bonuses=((bk, 2.0),),
    ).build_optimizer(economy)
    mask = (economy.df_production["building"] == bk).to_numpy()
    base = (economy.goods_output_matrix() - economy.goods_input_matrix())[mask]
    np.testing.assert_allclose(optimizer.goods_matrix[mask], base * 2.0)


def test_optimize_chain_returns_state(economy: Economy, automation_scenario: Scenario):
    state = automation_scenario.optimize(economy)
    assert isinstance(state, EconomyState)
    assert state.building_levels.shape == (len(economy.building_index()),)


def test_optimize_chain_satisfies_produce(
    economy: Economy, automation_scenario: Scenario
):
    optimizer = automation_scenario.build_optimizer(economy)
    state = optimizer.linprog()
    idx = optimizer.goods_index().index(TERMINAL_GOOD)
    net = float(state.building_levels @ optimizer.goods_matrix[:, idx])
    assert net >= automation_scenario.target_amount - 1e-6


def test_optimize_chain_unbounded(economy: Economy):
    # maximising GDP with no construction cap is unbounded.
    with pytest.raises(ValueError, match="Optimization failed"):
        Scenario(
            terminal_good=TERMINAL_GOOD,
            target_amount=1.0,
            objective="gdp",
        ).optimize(economy)


def test_nominal_optimizer_result_attribute(solved):
    optimizer, _state = solved
    assert optimizer.result is not None
    assert hasattr(optimizer.result, "ineqlin")


def test_nominal_optimizer_result_cleared_on_reset(economy: Economy):
    optimizer = Scenario(
        terminal_good=TERMINAL_GOOD, target_amount=1.0
    ).build_optimizer(economy)
    optimizer.linprog()
    assert optimizer.result is not None
    optimizer.reset()
    assert optimizer.result is None


def test_upstream_tree_invalid_good(economy: Economy):
    with pytest.raises(ValueError, match="not found in goods index"):
        upstream_tree(economy, "not_a_real_good")


def test_upstream_tree_recipe(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    assert isinstance(tree, SupplyChainNode)
    assert tree.good == TERMINAL_GOOD
    assert not tree.is_raw
    assert len(tree.producers) > 0
    for producer in tree.iter_producers():
        assert isinstance(producer, ProducerNode)
        assert producer.building
        assert producer.level == 1.0
        assert len(producer.outputs) > 0


def test_upstream_tree_raw_good(economy: Economy):
    tree = upstream_tree(economy, RAW_GOOD)
    assert tree.is_raw is True
    assert tree.producers == ()


def test_upstream_tree_realized_filters_inactive(economy: Economy, solved):
    optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    assert not tree.is_raw
    levels = state.building_levels
    for producer in tree.iter_producers():
        row = economy.building_index().index(producer.config)
        assert levels[row] > 1e-10


def test_upstream_tree_realized_scales_flows(economy: Economy, solved):
    optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    out_mat = economy.goods_output_matrix()
    goods_index = economy.goods_index()
    key_to_i = {k: i for i, k in enumerate(economy.building_index())}
    for producer in tree.iter_producers():
        i = key_to_i[producer.config]
        level = float(state.building_levels[i])
        for good, amount in producer.outputs.items():
            j = goods_index.index(good)
            assert amount == pytest.approx(out_mat[i, j] * level)


def test_upstream_tree_realized_employment_matches(economy: Economy, solved):
    _optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    emp_vec = economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    key_to_i = {k: i for i, k in enumerate(economy.building_index())}
    collected = {}
    for producer in tree.iter_producers():
        if producer.config not in collected:
            collected[producer.config] = producer
    total = sum(
        emp_vec[key_to_i[p.config]] * float(state.building_levels[key_to_i[p.config]])
        for p in collected.values()
    )
    assert total == pytest.approx(float(np.sum(state.pops)), rel=1e-6)


def test_iter_producers_yields_producers(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    producers = list(tree.iter_producers())
    assert len(producers) > 0
    # A configuration producing several goods appears once per good-node, so
    # iter_producers may repeat configs; collect_producers de-duplicates them.
    yielded = [p.config for p in producers]
    collected = tree.collect_producers()
    assert len(collected) <= len(yielded)
    assert set(yielded) == set(collected)
    assert len(collected) == len(set(collected))


def test_to_mermaid_recipe(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    m = tree.to_mermaid()
    assert m.startswith("flowchart LR")
    assert TERMINAL_GOOD in m
    # recipe mode has aggregated good→good edges (no producer nodes)
    assert "((" in m
    assert '["' not in m


def test_to_mermaid_realized(economy: Economy, solved):
    optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    m = tree.to_mermaid(realized=True)
    assert m.startswith("flowchart LR")
    assert TERMINAL_GOOD in m
    # realized mode has producer box nodes with level labels
    assert '["' in m
    assert "lvl=" in m


def test_to_mermaid_direction(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    m = tree.to_mermaid(direction="TD")
    assert m.startswith("flowchart TD")


def test_to_mermaid_title(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    m = tree.to_mermaid(title="My Diagram")
    assert "%% My Diagram" in m


def test_to_mermaid_dashed_cycle_edges(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    m = tree.to_mermaid()
    # Victoria 3 has mutual dependencies (e.g. steel ↔ tools); these render
    # as dashed edges.
    assert "-.->" in m


def test_to_mermaid_recipe_vs_realized_differ(economy: Economy, solved):
    optimizer, state = solved
    recipe = upstream_tree(economy, TERMINAL_GOOD)
    realised = upstream_tree(economy, TERMINAL_GOOD, state)
    m_recipe = recipe.to_mermaid()
    m_realised = realised.to_mermaid(realized=True)
    assert m_recipe != m_realised


def test_to_mermaid_raw_good(economy: Economy):
    tree = upstream_tree(economy, RAW_GOOD)
    m = tree.to_mermaid()
    assert m.startswith("flowchart LR")
    assert RAW_GOOD in m
    assert "[raw]" in m


def test_chain_depth_raw(economy: Economy):
    tree = upstream_tree(economy, RAW_GOOD)
    assert tree.chain_depth() == 0


def test_chain_depth_recipe(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    assert tree.chain_depth() > 0


def test_chain_depth_realized(economy: Economy, solved):
    _optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    assert tree.chain_depth() > 0


def test_count_raw_inputs_raw(economy: Economy):
    tree = upstream_tree(economy, RAW_GOOD)
    assert tree.count_raw_inputs() == 1


def test_count_raw_inputs_recipe(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    assert tree.count_raw_inputs() > 0


def test_count_raw_inputs_realized(economy: Economy, solved):
    _optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    assert tree.count_raw_inputs() > 0


def test_collect_good_nodes(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    nodes = tree.collect_good_nodes()
    assert TERMINAL_GOOD in nodes
    assert len(nodes) > 1


def test_collect_producers(economy: Economy):
    tree = upstream_tree(economy, TERMINAL_GOOD)
    producers = tree.collect_producers()
    assert len(producers) > 0
    assert all(isinstance(p, ProducerNode) for p in producers.values())


def test_value_added_breakdown_invalid_by(economy: Economy, solved):
    _optimizer, state = solved
    with pytest.raises(ValueError, match="by must be"):
        value_added_breakdown(economy, state, by="bogus")


def test_value_added_breakdown_invalid_good(economy: Economy, solved):
    _optimizer, state = solved
    with pytest.raises(ValueError, match="not found in goods index"):
        value_added_breakdown(economy, state, good="not_a_real_good")


def test_value_added_breakdown_config(economy: Economy, solved):
    _optimizer, state = solved
    df = value_added_breakdown(economy, state)
    expected = [
        "config",
        "building",
        "production_method",
        "level",
        "output_value",
        "input_cost",
        "gdp",
        "employment",
        "construction_cost",
    ]
    assert list(df.columns) == expected
    assert (df["level"] > 0).all()
    assert df["gdp"].is_monotonic_decreasing
    assert df["gdp"].sum() == pytest.approx(state.gdp_weekly, rel=1e-6)


def test_value_added_breakdown_good(economy: Economy, solved):
    _optimizer, state = solved
    df = value_added_breakdown(economy, state, by="good")
    expected = [
        "good",
        "output_value",
        "input_cost",
        "gdp",
        "employment",
        "construction_cost",
    ]
    assert list(df.columns) == expected
    assert df["gdp"].is_monotonic_decreasing
    # allocation preserves the GDP total.
    assert df["gdp"].sum() == pytest.approx(state.gdp_weekly, rel=1e-6)


def test_value_added_breakdown_chain_subset(economy: Economy, solved):
    _optimizer, state = solved
    df = value_added_breakdown(economy, state, good=TERMINAL_GOOD)
    assert list(df.columns)[0] == "config"
    assert df["gdp"].sum() == pytest.approx(state.gdp_weekly, rel=1e-3)
    assert df["gdp"].sum() >= 0


def test_bottleneck_columns(economy: Economy, solved):
    _optimizer, state = solved
    df = bottleneck(economy, state)
    expected = ["good", "input_cost", "cost_share", "net_supply", "import_marginal"]
    assert list(df.columns) == expected
    assert df["input_cost"].is_monotonic_decreasing
    assert (df["cost_share"] >= 0).all()
    assert (df["cost_share"] <= 1).all()


def test_bottleneck_with_optimizer(economy: Economy, solved):
    optimizer, state = solved
    df = bottleneck(economy, state, good=TERMINAL_GOOD, optimizer=optimizer)
    assert df["import_marginal"].notna().any()  # pyright: ignore[reportGeneralTypeIssues]
    assert (df["cost_share"] >= 0).all()


def test_bottleneck_without_optimizer(economy: Economy, solved):
    _optimizer, state = solved
    df = bottleneck(economy, state, good=TERMINAL_GOOD)
    assert df["import_marginal"].isna().all()  # pyright: ignore[reportGeneralTypeIssues]


def test_bottleneck_invalid_good(economy: Economy, solved):
    _optimizer, state = solved
    with pytest.raises(ValueError, match="not found in goods index"):
        bottleneck(economy, state, good="not_a_real_good")


def test_compare_scenarios(economy: Economy):
    scenarios = [
        Scenario(name="automation", terminal_good=TERMINAL_GOOD, target_amount=1.0),
        Scenario(
            name="bonus",
            terminal_good=TERMINAL_GOOD,
            target_amount=1.0,
            throughput_bonuses=(("building_automotive_industry", 2.0),),
        ),
        Scenario(
            name="min-construction",
            terminal_good=TERMINAL_GOOD,
            target_amount=1.0,
            objective="construction_cost",
        ),
        Scenario(
            name="unbounded",
            terminal_good=TERMINAL_GOOD,
            target_amount=1.0,
            objective="gdp",
        ),
    ]
    df = compare_scenarios(economy, scenarios)
    expected = [
        "name",
        "terminal_good",
        "objective",
        "target_amount",
        "base_price",
        "annual_gdp",
        "employment",
        "construction_cost",
        "gdp_per_capita",
        "gdp_per_construction",
        "n_active_buildings",
        "chain_depth",
        "n_raw_inputs",
        "bottleneck_good",
        "bottleneck_cost_share",
        "bottleneck_marginal",
        "error",
    ]
    assert list(df.columns) == expected
    assert len(df) == 4
    # automation / bonus / min-construction solved; gdp is unbounded.
    assert df.iloc[0]["error"] == ""
    assert df.iloc[3]["error"]  # non-empty error message
    assert not pd.isna(df.iloc[0]["annual_gdp"])
    assert pd.isna(df.iloc[3]["annual_gdp"])
    # throughput bonus lowers employment for the same output.
    assert df.iloc[1]["employment"] < df.iloc[0]["employment"]
    # chain columns populated for solved scenarios.
    assert df.iloc[0]["n_active_buildings"] > 0
    assert df.iloc[0]["chain_depth"] > 0
    assert df.iloc[0]["n_raw_inputs"] > 0
    assert df.iloc[0]["base_price"] == 100.0
    # chain columns zeroed for failed scenarios.
    assert df.iloc[3]["n_active_buildings"] == 0
    assert df.iloc[3]["chain_depth"] == 0


def test_compare_scenarios_empty(economy: Economy):
    df = compare_scenarios(economy, [])
    assert df.empty


def test_producible_goods(economy: Economy):
    goods = economy.producible_goods()
    assert len(goods) > 0
    assert TERMINAL_GOOD in goods
    # raw goods (no producers) are excluded.
    assert RAW_GOOD not in goods


def test_producible_goods_matches_output_matrix(economy: Economy):
    out_mat = economy.goods_output_matrix()
    goods_index = economy.goods_index()
    expected = [g for j, g in enumerate(goods_index) if (out_mat[:, j] > 0).any()]
    assert economy.producible_goods() == expected
