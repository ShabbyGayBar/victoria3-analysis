import numpy as np
import pandas as pd
import pytest

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.analysis.supply_chain import (
    ProducerNode,
    SupplyChainNode,
    bottleneck,
    compare_scenarios,
    optimize_chain,
    upstream_tree,
    value_added_breakdown,
)
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.scenario import Scenario

TERMINAL_GOOD = "automobiles"
RAW_GOOD = "manowars"
RESOURCE_LIMITED_GROUPS = frozenset(
    {
        "bg_mining",
        "bg_logging",
        "bg_rubber",
        "bg_fishing",
        "bg_whaling",
        "bg_oil_extraction",
    }
)


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


@pytest.fixture(scope="module")
def automation_scenario() -> Scenario:
    return Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="automation")


@pytest.fixture(scope="module")
def solved(economy: Economy, automation_scenario: Scenario):
    optimizer = NominalOptimizer(economy)
    state = optimizer.solve(automation_scenario)
    return optimizer, state


def test_optimize_chain_returns_state(economy: Economy, automation_scenario: Scenario):
    state = optimize_chain(economy, automation_scenario)
    assert isinstance(state, EconomyState)
    assert state.building_levels.shape == (len(economy.building_index()),)


def test_optimize_chain_satisfies_produce(
    economy: Economy, automation_scenario: Scenario
):
    state = optimize_chain(economy, automation_scenario)
    idx = economy.goods_index().index(TERMINAL_GOOD)
    net = float(
        state.building_levels @ automation_scenario.goods_matrix(economy)[:, idx]
    )
    assert net >= automation_scenario.produce[0][1] - 1e-6


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
    _optimizer, state = solved
    tree = upstream_tree(economy, TERMINAL_GOOD, state)
    assert not tree.is_raw
    levels = state.building_levels
    for producer in tree.iter_producers():
        row = economy.building_index().index(producer.config)
        assert levels[row] > 1e-10


def test_upstream_tree_realized_scales_flows(economy: Economy, solved):
    _optimizer, state = solved
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
    emp_vec = economy.employment_vector()
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


def test_upstream_tree_scenario_bonus_consistent(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="automation",
        throughput_bonuses=(("building_automotive_industry", 2.0),),
    )
    state = optimize_chain(economy, scenario)
    tree = upstream_tree(economy, TERMINAL_GOOD, state, scenario)
    out_mat = scenario.goods_output_matrix(economy)
    goods_index = economy.goods_index()
    key_to_i = {k: i for i, k in enumerate(economy.building_index())}
    for producer in tree.iter_producers():
        i = key_to_i[producer.config]
        level = float(state.building_levels[i])
        for good, amount in producer.outputs.items():
            j = goods_index.index(good)
            assert amount == pytest.approx(out_mat[i, j] * level)
    # without the scenario the same state renders unscaled flows, so the
    # bonused building's outputs differ by the bonus multiplier.
    raw_tree = upstream_tree(economy, TERMINAL_GOOD, state)
    adjusted = tree.collect_producers()
    raw = raw_tree.collect_producers()
    auto_configs = [
        config
        for config in set(adjusted) & set(raw)
        if raw[config].building == "building_automotive_industry"
    ]
    assert auto_configs
    config = auto_configs[0]
    for good, amount in adjusted[config].outputs.items():
        assert amount == pytest.approx(2.0 * raw[config].outputs[good])


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
    _optimizer, state = solved
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
    _optimizer, state = solved
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


def test_value_added_breakdown_scenario_bonus_consistent(economy: Economy):
    scenario = Scenario(
        produce=((TERMINAL_GOOD, 1.0),),
        objective="automation",
        throughput_bonuses=(("building_automotive_industry", 2.0),),
    )
    state = optimize_chain(economy, scenario)
    # with the scenario, GDP totals match the bonus-adjusted objective vector.
    df = value_added_breakdown(economy, state, scenario=scenario)
    adjusted = float(np.dot(state.building_levels, scenario.gdp_vector(economy)))
    assert df["gdp"].sum() == pytest.approx(adjusted, rel=1e-6)
    # without it, totals match the raw matrices instead (and differ).
    df_raw = value_added_breakdown(economy, state)
    raw = float(
        np.dot(
            state.building_levels,
            (economy.goods_output_matrix() - economy.goods_input_matrix())
            @ economy.base_prices(),
        )
    )
    assert df_raw["gdp"].sum() == pytest.approx(raw, rel=1e-6)
    assert not np.isclose(adjusted, raw, rtol=1e-6)


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
    assert df["import_marginal"].notna().to_numpy().any()
    assert (df["cost_share"] >= 0).all()


def test_bottleneck_without_optimizer(economy: Economy, solved):
    _optimizer, state = solved
    df = bottleneck(economy, state, good=TERMINAL_GOOD)
    assert df["import_marginal"].isna().to_numpy().all()


def test_bottleneck_invalid_good(economy: Economy, solved):
    _optimizer, state = solved
    with pytest.raises(ValueError, match="not found in goods index"):
        bottleneck(economy, state, good="not_a_real_good")


def test_compare_scenarios(economy: Economy):
    scenarios = [
        Scenario(name="automation", produce=((TERMINAL_GOOD, 1.0),)),
        Scenario(
            name="bonus",
            produce=((TERMINAL_GOOD, 1.0),),
            throughput_bonuses=(("building_automotive_industry", 2.0),),
        ),
        Scenario(
            name="min-construction",
            produce=((TERMINAL_GOOD, 1.0),),
            objective="construction_cost",
        ),
        Scenario(
            name="unbounded",
            produce=((TERMINAL_GOOD, 1.0),),
            objective="gdp",
        ),
    ]
    df = compare_scenarios(economy, scenarios)
    production = economy.df_production
    resource_mask = production["building_group"].isin(tuple(RESOURCE_LIMITED_GROUPS))
    resource_buildings = list(
        dict.fromkeys(production.loc[resource_mask, "building"].astype(str))
    )
    level_columns = [f"level_{building}" for building in resource_buildings]
    expected = [
        "name",
        "produce",
        "objective",
        "base_price",
        "annual_gdp",
        "employment",
        "construction_cost",
        "gdp_per_capita",
        "gdp_per_construction",
        "era_cap",
        "arable_land_consumption",
        *level_columns,
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
    assert df.iloc[0]["produce"] == f"{TERMINAL_GOOD}=1"
    level_start = expected.index(level_columns[0])
    assert list(df.columns[level_start : level_start + len(level_columns)]) == (
        level_columns
    )
    assert level_columns
    # Every discovered building level aggregates all PM configurations for it.
    state = optimize_chain(economy, scenarios[0])
    for building, column in zip(resource_buildings, level_columns):
        mask = production["building"].astype(str) == building
        expected_level = float(np.sum(state.building_levels[mask.to_numpy()]))
        assert df.iloc[0][column] == pytest.approx(expected_level)
    # The unbounded scenario has no solved state, so all dynamic values are NaN.
    assert df.iloc[3][level_columns].isna().all()
    # chain columns zeroed for failed scenarios.
    assert df.iloc[3]["n_active_buildings"] == 0
    assert df.iloc[3]["chain_depth"] == 0


def test_compare_scenarios_empty_basket(economy: Economy):
    # a produce-free scenario solves trivially; chain columns are zeroed.
    df = compare_scenarios(economy, [Scenario(objective="construction_cost")])
    assert len(df) == 1
    assert df.iloc[0]["error"] == ""
    assert df.iloc[0]["n_active_buildings"] == 0
    assert df.iloc[0]["bottleneck_good"] == ""
    assert pd.isna(df.iloc[0]["base_price"])
    level_columns = [column for column in df.columns if column.startswith("level_")]
    assert level_columns
    assert (df.loc[0, level_columns] == 0.0).all()


def test_compare_scenarios_solves_each_scenario_once(
    economy: Economy, monkeypatch: pytest.MonkeyPatch
):
    calls = 0
    original_solve = NominalOptimizer.solve

    def counted_solve(optimizer: NominalOptimizer, scenario: Scenario):
        nonlocal calls
        calls += 1
        return original_solve(optimizer, scenario)

    monkeypatch.setattr(NominalOptimizer, "solve", counted_solve)
    compare_scenarios(
        economy,
        [Scenario(produce=((TERMINAL_GOOD, 1.0),), objective="automation")],
    )
    assert calls == 1


def test_compare_scenarios_without_building_group(economy: Economy):
    production = economy.df_production.drop(columns="building_group")
    custom_economy = Economy(
        df_production=production,
        df_goods=economy.df_goods,
        df_pop_types=economy.df_pop_types,
    )
    df = compare_scenarios(custom_economy, [Scenario(objective="construction_cost")])

    assert len(df) == 1
    assert not any(column.startswith("level_") for column in df.columns)
    assert df.iloc[0]["error"] == ""


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
