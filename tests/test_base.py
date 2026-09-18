from dataclasses import FrozenInstanceError
from typing import Any, cast

import numpy as np
import pytest

from vic3_analysis import BaseOptimizer, LinearProblem, MarketProblem, Scenario
from vic3_analysis.analysis.economy import Economy
from vic3_analysis.optimize.nominal import NominalOptimizer


@pytest.fixture(scope="module")
def economy() -> Economy:
    return Economy()


def _context_scenario(field: str, value: tuple[tuple[str, float], ...]) -> Scenario:
    if field == "imports":
        return Scenario(imports=value)
    if field == "exports":
        return Scenario(exports=value)
    if field == "pop_needs":
        return Scenario(pop_needs=value)
    raise ValueError(f"Unknown context field: {field}")


def test_base_optimizer_is_abstract(economy: Economy):
    with pytest.raises(TypeError):
        cast(Any, BaseOptimizer)(economy)


def test_public_problem_types_are_dataclasses():
    assert LinearProblem.__dataclass_fields__
    assert MarketProblem.__dataclass_fields__


def test_compiled_problem_is_immutable(economy: Economy):
    problem = NominalOptimizer(economy).compile(Scenario())
    with pytest.raises(FrozenInstanceError):
        setattr(problem, "scenario", Scenario(name="replacement"))  # noqa: B010
    with pytest.raises(ValueError, match="read-only"):
        problem.gdp_vector[0] = 0.0
    with pytest.raises(TypeError):
        cast(Any, problem.inequality_slices)["extra"] = slice(0, 1)


def test_compiled_access_requires_problem(economy: Economy):
    optimizer = NominalOptimizer(economy)
    for attribute in (
        "goods_input_matrix",
        "goods_output_matrix",
        "goods_matrix",
        "gdp_vector",
        "throughput_multipliers",
    ):
        with pytest.raises(ValueError, match="not compiled or solved"):
            getattr(optimizer, attribute)


def test_common_context_and_cumulative_bonuses(economy: Economy):
    building = str(economy.df_production["building"].iloc[0])
    optimizer = NominalOptimizer(economy)
    problem = optimizer.compile(
        Scenario(
            objective="construction_cost",
            import_limit=None,
            throughput_bonuses=((building, 2.0), (building, 1.5)),
            imports=(("tools", 2.0), ("tools", 3.0)),
            exports=(("coal", 4.0),),
            pop_needs=(("grain", 5.0),),
        )
    )
    mask = (economy.df_production["building"] == building).to_numpy()
    np.testing.assert_allclose(
        problem.output_matrix[mask], economy.goods_output_matrix()[mask] * 3.0
    )
    np.testing.assert_allclose(
        problem.input_matrix[mask], economy.goods_input_matrix()[mask] * 3.0
    )
    np.testing.assert_allclose(
        problem.net_matrix, problem.output_matrix - problem.input_matrix
    )
    np.testing.assert_allclose(
        problem.gdp_vector, problem.net_matrix @ economy.base_prices()
    )
    goods = economy.goods_index()
    assert problem.imports[goods.index("tools")] == pytest.approx(5.0)
    assert problem.exports[goods.index("coal")] == pytest.approx(4.0)
    assert problem.pop_needs[goods.index("grain")] == pytest.approx(5.0)
    assert optimizer.goods_input_matrix is problem.input_matrix
    assert optimizer.goods_output_matrix is problem.output_matrix
    assert optimizer.goods_matrix is problem.net_matrix
    assert optimizer.gdp_vector is problem.gdp_vector
    assert optimizer.throughput_multipliers is problem.throughput_multipliers


@pytest.mark.parametrize("field", ("imports", "exports", "pop_needs"))
def test_context_rejects_unknown_goods(economy: Economy, field: str):
    with pytest.raises(ValueError, match="not found in goods index"):
        NominalOptimizer(economy).compile(
            _context_scenario(field, (("not_a_good", 1.0),))
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("imports", (("tools", -1.0),)),
        ("exports", (("tools", np.nan),)),
        ("pop_needs", (("tools", np.inf),)),
    ),
)
def test_context_rejects_invalid_amounts(
    economy: Economy, field: str, value: tuple[tuple[str, float], ...]
):
    with pytest.raises(ValueError, match="finite non-negative"):
        NominalOptimizer(economy).compile(_context_scenario(field, value))


@pytest.mark.parametrize(
    "entries",
    (
        cast(Any, (("tools",),)),
        cast(Any, ((1, 1.0),)),
        cast(Any, (("tools", object()),)),
    ),
)
def test_context_rejects_malformed_entries(economy: Economy, entries: Any):
    with pytest.raises(ValueError):
        NominalOptimizer(economy).compile(Scenario(imports=entries))


def test_context_rejects_overflowing_duplicate_total(economy: Economy):
    maximum = np.finfo(np.float64).max
    with pytest.raises(ValueError, match="totals must remain finite"):
        NominalOptimizer(economy).compile(
            Scenario(imports=(("tools", maximum), ("tools", maximum)))
        )


def test_inequality_compilation_and_named_slices(economy: Economy):
    scenario = Scenario(
        produce=(("automobiles", 1.0), ("steel", 2.0)),
        objective="construction_cost",
        construction_cost_cap=5000.0,
        employment_cap=1000.0,
        building_limits=(("building_dye_plantation", 0.0),),
        arable_land_cap=25.0,
        min_infrastructure=5.0,
    )
    problem = NominalOptimizer(economy).compile(scenario)
    assert problem.A_ub is not None
    assert problem.b_ub is not None
    assert tuple(problem.inequality_slices) == (
        "import_limit",
        "construction_cost_cap",
        "employment_cap",
        "produce",
        "building_limits",
        "arable_land_cap",
        "min_infrastructure",
    )
    import_rows = problem.inequality_slices["import_limit"]
    np.testing.assert_allclose(problem.A_ub[import_rows], -problem.net_matrix.T)
    produce_rows = problem.inequality_slices["produce"]
    np.testing.assert_array_equal(problem.b_ub[produce_rows], [-1.0, -2.0])
    assert problem.A_ub.shape[0] == problem.b_ub.shape[0]


def test_equality_compilation_and_named_slices(economy: Economy):
    median = economy.df_production["era"].median()
    assert isinstance(median, float)
    era = int(median)
    group = str(economy.df_production["building_group"].iloc[0])
    production_method = str(economy.df_production["production_method"].iloc[0]).split(
        "+"
    )[0]
    problem = NominalOptimizer(economy).compile(
        Scenario(
            era_cap=era,
            banned_pms=(production_method,),
            banned_building_groups=(group,),
            urbanization_per_center=100.0,
        )
    )
    assert problem.A_eq is not None
    assert problem.b_eq is not None
    assert tuple(problem.equality_slices) == (
        "era_cap",
        "banned_pms",
        "banned_building_groups",
        "urbanization_per_center",
    )
    np.testing.assert_array_equal(problem.b_eq, np.zeros(4))
    assert problem.A_eq.shape == (4, len(economy.building_index()))


def test_empty_constraint_compilation(economy: Economy):
    problem = NominalOptimizer(economy).compile(
        Scenario(objective="construction_cost", import_limit=None)
    )
    assert problem.A_ub is None
    assert problem.b_ub is None
    assert problem.A_eq is None
    assert problem.b_eq is None
    assert not problem.inequality_slices
    assert not problem.equality_slices


def test_unknown_produce_good_raises_during_compilation(economy: Economy):
    with pytest.raises(ValueError, match="not found in goods index"):
        NominalOptimizer(economy).compile(Scenario(produce=(("not_a_real_good", 1.0),)))


def test_named_constraint_stack_rejects_mismatched_rows():
    with pytest.raises(ValueError, match="mismatched rows"):
        NominalOptimizer._stack_named([("bad", np.ones((2, 1)), np.ones(1))])
