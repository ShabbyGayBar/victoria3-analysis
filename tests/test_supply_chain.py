from __future__ import annotations

from dataclasses import FrozenInstanceError

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from vic3_analysis import (
    SupplyChainAnalyzer,
    SupplyChainResult,
    SupplyChainSweepResult,
    sweep_supply_chains,
)
from vic3_analysis.analysis.economy import Economy
from vic3_analysis.analysis.supply_chain.result import (
    ALTERNATIVE_COLUMNS,
    CONSTRAINT_COLUMNS,
    FLOW_COLUMNS,
    GOOD_COLUMNS,
    PROCESS_COLUMNS,
    SUMMARY_FIELDS,
    WORKFORCE_COLUMNS,
)
from vic3_analysis.analysis.supply_chain.sweep import SWEEP_COLUMNS
from vic3_analysis.optimize.scenario import Scenario


def _production_row(
    building: str,
    production_method: str,
    *,
    era: int = 1,
    group: str = "bg_manufacturing",
    parent_group: str = "bg_manufacturing",
    employment: float = 100.0,
    construction: float = 10.0,
    infrastructure: float = 1.0,
    laborers: float | None = None,
    engineers: float | None = None,
    discoverable: bool = False,
    depletable: bool = False,
    **goods: float,
) -> dict[str, object]:
    laborer_count = employment if laborers is None else laborers
    engineer_count = 0.0 if engineers is None else engineers
    row: dict[str, object] = {
        "building": building,
        "production_method": production_method,
        "building_group": group,
        "parent_group": parent_group,
        "land_usage": "land" if group == "bg_agriculture" else "",
        "is_subsistence": False,
        "discoverable_resource": discoverable,
        "depletable_resource": depletable,
        "era": era,
        "employment": employment,
        "employment_laborers": laborer_count,
        "employment_engineers": engineer_count,
        "construction_cost": construction,
        "infrastructure_usage_per_level": infrastructure,
    }
    row.update({f"goods_{good}": amount for good, amount in goods.items()})
    return row


@pytest.fixture
def economy() -> Economy:
    goods = ["ore", "metal", "tools", "widget", "byproduct", "luxury", "dead"]
    rows = [
        _production_row(
            "building_mine",
            "pm_mine",
            group="bg_mining",
            parent_group="bg_extraction",
            employment=80.0,
            construction=8.0,
            discoverable=True,
            ore=10.0,
        ),
        _production_row(
            "building_quarry",
            "pm_quarry",
            group="bg_mining",
            parent_group="bg_extraction",
            employment=100.0,
            construction=10.0,
            depletable=True,
            ore=8.0,
        ),
        _production_row(
            "building_smelter",
            "pm_smelter",
            employment=200.0,
            construction=20.0,
            ore=-10.0,
            tools=-1.0,
            metal=10.0,
            byproduct=2.0,
        ),
        _production_row(
            "building_toolworks",
            "pm_tools",
            employment=60.0,
            construction=8.0,
            metal=-2.0,
            tools=2.0,
        ),
        _production_row(
            "building_widget_fast",
            "pm_widget_fast",
            employment=150.0,
            construction=30.0,
            metal=-4.0,
            widget=10.0,
        ),
        _production_row(
            "building_widget_slow",
            "pm_widget_slow",
            era=2,
            employment=120.0,
            construction=25.0,
            metal=-3.0,
            widget=5.0,
        ),
        _production_row(
            "building_widget_forbidden",
            "pm_widget_forbidden",
            group="bg_forbidden",
            employment=140.0,
            construction=40.0,
            metal=-3.0,
            widget=6.0,
        ),
        _production_row(
            "building_widget_manual",
            "pm_widget_manual",
            employment=200.0,
            construction=80.0,
            metal=-3.0,
            widget=4.0,
        ),
        _production_row(
            "building_luxury",
            "pm_luxury",
            employment=1.0,
            construction=1.0,
            luxury=1.0,
        ),
    ]
    production = pd.DataFrame(rows).fillna(0.0)
    for good in goods:
        column = f"goods_{good}"
        if column not in production:
            production[column] = 0.0
    goods_table = pd.DataFrame(
        {
            "key": goods,
            "cost": [10.0, 20.0, 30.0, 50.0, 5.0, 100.0, 1.0],
        }
    )
    pops = pd.DataFrame(
        {
            "key": ["laborers", "engineers"],
            "start_quality_of_life": [10.0, 20.0],
        }
    )
    return Economy(
        df_production=production,
        df_goods=goods_table,
        df_pop_types=pops,
    )


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        produce=(("widget", 100.0),),
        objective="construction_cost",
        name="widgets",
    )


@pytest.fixture
def result(economy: Economy, scenario: Scenario) -> SupplyChainResult:
    return SupplyChainAnalyzer(economy, scenario, "widget").run()


def test_analyzer_validates_single_matching_positive_target(economy: Economy):
    with pytest.raises(ValueError, match="not found"):
        SupplyChainAnalyzer(economy, Scenario(produce=(("widget", 1.0),)), "missing")
    with pytest.raises(ValueError, match="exactly one"):
        SupplyChainAnalyzer(economy, Scenario(), "widget")
    with pytest.raises(ValueError, match="exactly one"):
        SupplyChainAnalyzer(
            economy,
            Scenario(produce=(("widget", 1.0), ("metal", 1.0))),
            "widget",
        )
    with pytest.raises(ValueError, match="must match"):
        SupplyChainAnalyzer(economy, Scenario(produce=(("metal", 1.0),)), "widget")
    with pytest.raises(ValueError, match="positive finite"):
        SupplyChainAnalyzer(economy, Scenario(produce=(("widget", 0.0),)), "widget")
    with pytest.raises(ValueError, match="positive finite"):
        SupplyChainAnalyzer(economy, Scenario(produce=(("widget", np.inf),)), "widget")
    with pytest.raises(ValueError, match="positive finite"):
        SupplyChainAnalyzer(
            economy, Scenario(produce=(("widget", 1.0),)), "widget", tolerance=0
        )


def test_analyzer_rejects_unsupported_nominal_objective(economy: Economy):
    with pytest.raises(ValueError, match="nominal objectives"):
        SupplyChainAnalyzer(
            economy,
            Scenario(produce=(("widget", 1.0),), objective="gdp_per_capita"),
            "widget",
        )


def test_run_returns_immutable_snapshot(result: SupplyChainResult):
    assert isinstance(result, SupplyChainResult)
    assert result.state.building_levels.flags.writeable is False
    with pytest.raises(ValueError):
        result.state.building_levels[0] = 999.0
    with pytest.raises(FrozenInstanceError):
        setattr(result, "target_quantity", 2.0)  # noqa: B010
    graph = result.graph()
    graph.clear()
    assert result.graph().number_of_nodes() > 0


def test_result_isolated_from_later_economy_mutation(
    economy: Economy, scenario: Scenario
):
    result = SupplyChainAnalyzer(economy, scenario, "widget").run()
    original_building = str(result.production.iloc[0]["building"])
    original_rate = float(result.problem.output_matrix[0, 0])
    economy.df_production.loc[0, "building"] = "mutated"
    economy.df_production.loc[0, "goods_ore"] = 999.0
    assert result.production.iloc[0]["building"] == original_building
    assert result.problem.output_matrix[0, 0] == original_rate


def test_realized_graph_is_bipartite_and_retains_cycle(result: SupplyChainResult):
    graph = result.graph()
    assert nx.is_directed(graph)
    assert "good:widget" in graph
    assert "process:building_widget_fast+pm_widget_fast" in graph
    assert all(
        data["kind"] in {"good", "process"} for _, data in graph.nodes(data=True)
    )
    components = list(nx.strongly_connected_components(graph))
    cycle = next(component for component in components if "good:tools" in component)
    assert "good:metal" in cycle
    assert "process:building_smelter+pm_smelter" in cycle
    assert "process:building_toolworks+pm_tools" in cycle
    assert result.summary()["cyclic_component_count"] == 1
    assert not any(data.get("raw") for _, data in graph.nodes(data=True))


def test_flows_reconcile_with_adjusted_matrices(result: SupplyChainResult):
    flows = result.flows()
    assert list(flows.columns) == FLOW_COLUMNS
    config_positions = {key: i for i, key in enumerate(result.config_index)}
    good_positions = {key: i for i, key in enumerate(result.goods_index)}
    columns = (
        np.asarray(flows["process"], dtype=str),
        np.asarray(flows["good"], dtype=str),
        np.asarray(flows["role"], dtype=str),
        np.asarray(flows["unit_rate"], dtype=np.float64),
        np.asarray(flows["realized_amount"], dtype=np.float64),
        np.asarray(flows["price"], dtype=np.float64),
        np.asarray(flows["realized_value"], dtype=np.float64),
    )
    for process, good, role, unit_rate, amount, price, value in zip(
        *columns, strict=True
    ):
        i = config_positions[process]
        j = good_positions[good]
        matrix = (
            result.problem.input_matrix
            if role == "input"
            else result.problem.output_matrix
        )
        assert unit_rate == pytest.approx(matrix[i, j])
        assert amount == pytest.approx(matrix[i, j] * result.state.building_levels[i])
        assert value == pytest.approx(amount * price)


def test_tables_have_stable_schemas_and_reconcile(result: SupplyChainResult):
    processes = result.processes()
    goods = result.goods()
    workforce = result.workforce()
    assert list(processes.columns) == PROCESS_COLUMNS
    assert list(goods.columns) == GOOD_COLUMNS
    assert list(workforce.columns) == WORKFORCE_COLUMNS
    assert list(result.constraints().columns) == CONSTRAINT_COLUMNS
    assert list(result.alternatives().columns) == ALTERNATIVE_COLUMNS

    summary = result.summary()
    assert list(summary.index) == SUMMARY_FIELDS
    np.testing.assert_allclose(
        processes["value_added"].to_numpy(dtype=np.float64).sum(),
        summary["chain_gdp_weekly"],
    )
    np.testing.assert_allclose(
        result.state.gdp_weekly,
        summary["system_gdp_weekly"],
    )
    np.testing.assert_allclose(
        result.state.total_population,
        summary["system_employment"],
    )
    assert summary["target_quantity"] == 100.0
    assert summary["target_base_value"] == 5_000.0


def test_coproduct_contribution_is_exact_at_process_level(result: SupplyChainResult):
    processes = result.processes().set_index("building")
    smelter = processes.loc["building_smelter"]
    output_value = float(smelter["output_value"])  # pyright: ignore[reportArgumentType]
    input_cost = float(smelter["input_cost"])  # pyright: ignore[reportArgumentType]
    expected = output_value - input_cost
    assert smelter["value_added"] == pytest.approx(expected)  # pyright: ignore[reportGeneralTypeIssues]
    assert "allocation" not in result.goods().columns
    assert result.goods().set_index("good").loc["byproduct", "production"] > 0  # pyright: ignore[reportOperatorIssue]


def test_allowed_graph_respects_static_scenario_exclusions(economy: Economy):
    restricted = Scenario(
        produce=(("widget", 10.0),),
        objective="construction_cost",
        era_cap=1,
        banned_pms=("pm_widget_manual",),
        banned_building_groups=("bg_forbidden",),
        building_limits=(("building_quarry", 0.0),),
    )
    result = SupplyChainAnalyzer(economy, restricted, "widget").run()
    allowed = set(result.processes("allowed")["building"])
    assert "building_widget_slow" not in allowed
    assert "building_widget_forbidden" not in allowed
    assert "building_widget_manual" not in allowed
    assert "building_quarry" not in allowed
    assert "building_widget_fast" in allowed
    assert set(result.processes()["building"]) <= allowed


def test_alternatives_report_selected_and_resource_attributes(
    result: SupplyChainResult,
):
    widget = result.alternatives("widget")
    assert set(widget["building"]) == {
        "building_widget_fast",
        "building_widget_slow",
        "building_widget_forbidden",
        "building_widget_manual",
    }
    assert widget.loc[widget["selected"], "building"].tolist() == [
        "building_widget_fast"
    ]
    ore = result.alternatives("ore")
    assert np.asarray(ore["is_extractive"], dtype=bool).all()
    with pytest.raises(ValueError, match="not found"):
        result.alternatives("unknown")


def test_throughput_bonus_is_reflected_in_levels_and_edges(economy: Economy):
    base = SupplyChainAnalyzer(
        economy,
        Scenario(produce=(("widget", 100.0),), objective="construction_cost"),
        "widget",
    ).run()
    bonus = SupplyChainAnalyzer(
        economy,
        Scenario(
            produce=(("widget", 100.0),),
            objective="construction_cost",
            throughput_bonuses=(("building_widget_fast", 2.0),),
        ),
        "widget",
    ).run()
    base_process = base.processes().set_index("building").loc["building_widget_fast"]
    bonus_process = bonus.processes().set_index("building").loc["building_widget_fast"]
    assert bonus_process["throughput_multiplier"] == 2.0  # pyright: ignore[reportGeneralTypeIssues]
    assert bonus_process["level"] == pytest.approx(  # pyright: ignore[reportGeneralTypeIssues]
        float(base_process["level"]) / 2  # pyright: ignore[reportArgumentType]
    )
    edge = bonus.flows().query("good == 'widget' and role == 'output'").iloc[0]
    assert edge["unit_rate"] == 20.0


def test_fixed_imports_exports_and_needs_are_reported(economy: Economy):
    result = SupplyChainAnalyzer(
        economy,
        Scenario(
            produce=(("widget", 1.0),),
            objective="construction_cost",
            imports=(("ore", 3.0),),
            exports=(("byproduct", 2.0),),
            pop_needs=(("tools", 1.0),),
        ),
        "widget",
    ).run()
    goods = result.goods().set_index("good")
    assert goods.loc["ore", "imports"] == 3.0
    assert goods.loc["byproduct", "exports"] == 2.0
    assert goods.loc["tools", "pop_needs"] == 1.0


def test_constraints_have_labels_slacks_and_marginals(result: SupplyChainResult):
    constraints = result.constraints()
    produce = constraints.query("family == 'produce'").iloc[0]
    assert produce["label"] == "widget"
    assert produce["binding"]
    assert produce["slack"] == pytest.approx(0.0, abs=1e-8)
    assert np.isfinite(produce["solver_marginal"])
    bottlenecks = result.bottlenecks()
    assert (bottlenecks["binding"] == True).all()
    assert (bottlenecks["improvement_per_unit"] > 0).all()


def test_empty_table_schemas_are_stable(economy: Economy):
    result = SupplyChainAnalyzer(
        economy,
        Scenario(produce=(("luxury", 1.0),), objective="construction_cost"),
        "luxury",
    ).run()
    assert list(result.workforce().columns) == WORKFORCE_COLUMNS
    assert list(result.bottlenecks().columns) == CONSTRAINT_COLUMNS
    assert list(result.alternatives("dead").columns) == ALTERNATIVE_COLUMNS


def test_acyclic_chain_has_deterministic_condensation_depth(economy: Economy):
    result = SupplyChainAnalyzer(
        economy,
        Scenario(produce=(("luxury", 1.0),), objective="construction_cost"),
        "luxury",
    ).run()
    summary = result.summary()
    assert summary["cyclic_component_count"] == 0
    assert summary["cyclic_node_count"] == 0
    assert summary["condensation_depth"] == 1
    assert nx.is_directed_acyclic_graph(result.graph())


def test_infeasible_and_unbounded_analyses_raise(economy: Economy):
    with pytest.raises(ValueError, match="Optimization failed"):
        SupplyChainAnalyzer(
            economy,
            Scenario(produce=(("dead", 1.0),), objective="construction_cost"),
            "dead",
        ).run()
    with pytest.raises(ValueError, match="Optimization failed"):
        SupplyChainAnalyzer(
            economy,
            Scenario(produce=(("widget", 1.0),), objective="gdp"),
            "widget",
        ).run()


def test_mermaid_and_plots_are_deterministic_objects(result: SupplyChainResult):
    first = result.to_mermaid()
    second = result.to_mermaid()
    assert first == second
    assert first.startswith("flowchart LR")
    assert "classDef cyclic" in first
    assert "good:widget" not in first
    figures = [
        result.plot_network(),
        result.plot_network(view="allowed", metric="quantity"),
        result.plot_contributions(),
        result.plot_contributions(metric="employment", scope="system"),
        result.plot_goods_balance(),
        result.plot_constraints(),
    ]
    assert all(isinstance(figure, Figure) for figure in figures)
    for figure in figures:
        plt.close(figure)
    with pytest.raises(ValueError, match="metric"):
        result.plot_network(metric="unknown")
    pruned = result.to_mermaid(view="allowed", max_producers_per_good=1)
    assert "building_quarry" not in pruned
    assert "building_widget_manual" not in pruned


def test_graph_view_validation(result: SupplyChainResult):
    with pytest.raises(ValueError, match="view"):
        result.graph("unknown")
    with pytest.raises(ValueError, match="view"):
        result.processes("unknown")
    with pytest.raises(ValueError, match="view"):
        result.goods("unknown")
    with pytest.raises(ValueError, match="view"):
        result.flows("unknown")


def test_sweep_normalizes_value_preserves_order_and_names(economy: Economy):
    sweep = sweep_supply_chains(
        economy,
        Scenario(objective="construction_cost", name="baseline"),
        goods=["widget", "ore"],
        target_value=1_000.0,
        keep_results=True,
    )
    assert isinstance(sweep, SupplyChainSweepResult)
    assert list(sweep.summary.columns) == SWEEP_COLUMNS
    assert sweep.summary["good"].tolist() == ["widget", "ore"]
    assert sweep.summary["scenario"].tolist() == [
        "baseline:widget",
        "baseline:ore",
    ]
    np.testing.assert_allclose(sweep.summary["target_base_value"], 1_000.0)
    assert list(sweep.results) == ["widget", "ore"]
    assert sweep.result_for("widget").target_quantity == 20.0


def test_sweep_default_goods_use_economy_order(economy: Economy):
    sweep = sweep_supply_chains(
        economy,
        Scenario(objective="construction_cost"),
        target_value=100.0,
    )
    assert sweep.summary["good"].tolist() == economy.producible_goods()
    assert sweep.results == {}


def test_sweep_continues_after_failure(economy: Economy):
    sweep = sweep_supply_chains(
        economy,
        Scenario(objective="construction_cost"),
        goods=["dead", "ore"],
    )
    assert sweep.summary["status"].tolist() == ["failure", "success"]
    assert sweep.failures["good"].tolist() == ["dead"]
    assert sweep.failures.iloc[0]["error_type"] == "ValueError"
    with pytest.raises(KeyError, match="keep_results"):
        sweep.result_for("ore")


def test_sweep_validates_template_and_selection(economy: Economy):
    with pytest.warns(UserWarning, match="produce is ignored"):
        sweep = sweep_supply_chains(
            economy,
            Scenario(
                produce=(("ore", 1.0),),
                objective="construction_cost",
            ),
            goods=["widget"],
            target_value=1_000.0,
        )
    assert sweep.summary.loc[0, "terminal_good"] == "widget"
    assert sweep.summary.loc[0, "target_quantity"] == 20.0
    with pytest.raises(ValueError, match="positive finite"):
        sweep_supply_chains(economy, Scenario(), target_value=0.0)
    with pytest.raises(ValueError, match="duplicates"):
        sweep_supply_chains(economy, Scenario(), goods=["ore", "ore"])
    with pytest.raises(ValueError, match="not found"):
        sweep_supply_chains(economy, Scenario(), goods=["unknown"])
