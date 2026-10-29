# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Operating-loss financing with independently calculated household budgets."""

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

from vic3_analysis import (
    Economy,
    EconomyContext,
    EconomyState,
    EquilibriumError,
    EquilibriumOptimizer,
    MarketState,
    PopState,
    Scenario,
    SupplyChainEquilibriumOptimizer,
)
from vic3_analysis.optimize.equilibrium import _Search


@pytest.fixture(scope="module")
def subsidy_economy() -> Economy:
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["farm", "factory", "idle"],
                "production_method": ["pm"] * 3,
                "goods_food": [4.0, 0.0, 0.0],
                "goods_input": [-0.25, -1.0, 0.0],
                "employment_workers": [10_000.0, 5000.0, 0.0],
                "employment_engineers": [5000.0, 5000.0, 0.0],
                "employment_unpaid": [1000.0, 0.0, 0.0],
                "employment": [16_000.0, 10_000.0, 0.0],
            }
        ),
        df_goods=pd.DataFrame({"key": ["food", "input"], "cost": [1.0, 2.0]}),
        df_pop_types=pd.DataFrame(
            {
                "key": ["workers", "engineers", "unpaid"],
                "start_quality_of_life": [1, 1, 1],
                "wage_weight": [1.0, 2.0, 0.0],
                "consumption_mult": [1.0, 1.0, 1.0],
                "dependent_wage": [0.0052, 0.0104, 0.0],
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


def _with_policy(state: EconomyState, enabled: bool = True) -> EconomyState:
    context = replace(state.context, subsidize_operating_losses=enabled)
    return replace(
        state, context=context, market=MarketState(context, state.market_prices)
    )


def test_income_tax_includes_dependents_and_preserves_production(
    subsidy_economy: Economy,
):
    original = subsidy_economy.solve(np.ones(3), workforce_ratio=0.5)
    state = _with_policy(original)
    gross = np.array([[2.75, 2.75, 0], [0.5, 1.0, 0], [0, 0, 0]])
    tax = subsidy_economy.pop_income_tax(state)
    income = subsidy_economy.pop_income(state)
    np.testing.assert_allclose(subsidy_economy.pop_income(original), gross)
    np.testing.assert_allclose(tax, gross * (2 / 7))
    np.testing.assert_allclose(income, gross - tax)
    assert tax.sum() == pytest.approx(state.building_deficit.sum())
    np.testing.assert_array_equal(state.building_deficit, [0, 2, 0])
    assert state.gdp_weekly == original.gdp_weekly
    assert original.pop_income_tax is original.pop_income_before_tax is None


@pytest.mark.parametrize("losses", [0.0, 4.0, 4.0001])
def test_funding_boundary_and_zero_income(subsidy_economy: Economy, losses: float):
    state = subsidy_economy.solve(np.ones(3))
    flows = np.array([[4.0, 0.0], [-losses, 0.0], [0.0, 0.0]])
    context = replace(
        state.context, building_goods_flow=flows, subsidize_operating_losses=True
    )
    state = replace(state, context=context, market=MarketState(context, np.ones(2)))
    if losses > 4:
        with pytest.raises(ValueError, match="exceed total household income"):
            subsidy_economy.pop_income(state)
        with pytest.raises(ValueError, match="exceed total household income"):
            subsidy_economy.pop_income_tax(state)
    else:
        assert subsidy_economy.pop_income_tax(state).sum() == pytest.approx(losses)
        assert subsidy_economy.pop_income(state).sum() == pytest.approx(4 - losses)

    empty = _with_policy(subsidy_economy.solve(np.zeros(3)))
    np.testing.assert_array_equal(subsidy_economy.pop_income(empty), np.zeros((3, 3)))
    np.testing.assert_array_equal(
        subsidy_economy.pop_income_tax(empty), np.zeros((3, 3))
    )


def test_subsidized_empty_equilibrium_and_fixed_wealth(subsidy_economy: Economy):
    empty = subsidy_economy.solve(np.zeros(3), method="equilibrium")
    np.testing.assert_array_equal(empty.pop_income_tax, np.zeros((3, 3)))
    assert empty.equilibrium_diagnostics is not None
    assert empty.equilibrium_diagnostics.status == "converged"
    nominal = subsidy_economy.solve(np.array([1.0, 0.2, 0.0]), workforce_ratio=0.5)
    assert not nominal.context.subsidize_operating_losses
    context = EconomyContext(
        building_levels=nominal.building_levels,
        building_goods_flow=nominal.building_goods_flow,
        goods_import=nominal.goods_import,
        goods_export=nominal.goods_export,
        pops=nominal.pops,
        workforce_ratio=nominal.workforce_ratio,
    )
    assert context.subsidize_operating_losses
    market, households = subsidy_economy.evaluate_wealth(context, nominal.pop_wealth)
    evaluated = EconomyState(market.context, market, households)
    assert evaluated.pop_income is not None
    assert evaluated.pop_income_tax is not None
    np.testing.assert_allclose(
        evaluated.pop_income, subsidy_economy.pop_income(evaluated)
    )
    assert evaluated.pop_income_tax.sum() == pytest.approx(
        evaluated.building_deficit.sum()
    )


def test_subsidized_equilibrium_uses_disposable_income(subsidy_economy: Economy):
    untaxed = subsidy_economy.solve(
        np.array([1.0, 0.2, 0.0]),
        method="equilibrium",
        workforce_ratio=0.5,
        subsidize_operating_losses=False,
    )
    state = subsidy_economy.solve(
        np.array([1.0, 0.2, 0.0]),
        method="equilibrium",
        workforce_ratio=0.5,
    )
    assert state.context.subsidize_operating_losses
    assert state.equilibrium_diagnostics is not None
    assert state.equilibrium_diagnostics.status == "converged"
    assert not state.equilibrium_diagnostics.loss_buildings
    assert state.building_deficit.sum() > 0
    assert state.pop_income is not None
    assert state.pop_income_tax is not None
    assert state.pop_income_before_tax is not None
    np.testing.assert_allclose(state.pop_income, subsidy_economy.pop_income(state))
    np.testing.assert_allclose(
        state.pop_income_tax, subsidy_economy.pop_income_tax(state)
    )
    np.testing.assert_allclose(
        state.pop_income_before_tax, state.pop_income + state.pop_income_tax
    )
    assert state.pop_income_tax.sum() == pytest.approx(state.building_deficit.sum())
    assert state.average_wealth < untaxed.average_wealth
    market, households = subsidy_economy.iterate(
        state.context, state.market, state.households
    )
    assert market is state.market and households is state.households
    for values in (state.pop_income_tax, state.pop_income_before_tax):
        assert not values.flags.writeable
    assert untaxed.pop_income_tax is not None
    np.testing.assert_array_equal(untaxed.pop_income_tax, np.zeros((3, 3)))
    assert untaxed.equilibrium_diagnostics is not None
    assert untaxed.equilibrium_diagnostics.loss_buildings == (1,)


@pytest.mark.parametrize("factory_level, workforce_ratio", [(1.0, 1.0), (100.0, 0.5)])
def test_initial_funding_failure_retains_gross_snapshot(
    subsidy_economy: Economy, factory_level: float, workforce_ratio: float
):
    with pytest.raises(
        EquilibriumError, match="exceed total household income"
    ) as caught:
        subsidy_economy.solve(
            np.array([0.0, factory_level, 0.0]),
            method="equilibrium",
            workforce_ratio=workforce_ratio,
        )
    state = caught.value.state
    assert caught.value.diagnostics.status == "insufficient_income"
    assert caught.value.diagnostics.iterations == 0
    assert caught.value.diagnostics.loss_buildings == (1,)
    np.testing.assert_array_equal(
        state.pop_income, subsidy_economy.pop_income(_with_policy(state, False))
    )
    np.testing.assert_array_equal(state.pop_income_tax, np.zeros((3, 3)))
    with pytest.raises(ValueError, match="exceed total household income"):
        subsidy_economy.evaluate_wealth(state.context, state.pop_wealth)


def test_later_funding_failure_retains_failing_wealth(subsidy_economy: Economy):
    # At tier 3 food is expensive enough to finance inputs. The tax forces
    # households down; cheaper food then makes the next evaluation unfundable.
    model = replace(
        subsidy_economy,
        df_pop_types=subsidy_economy.df_pop_types.assign(dependent_wage=0.0),
    )
    with pytest.raises(EquilibriumError) as caught:
        model.solve(
            np.array([1.0, 0.6, 0.0]),
            method="equilibrium",
            initial_wealth=np.full((3, 3), 3),
            subsidize_operating_losses=True,
        )
    error = caught.value
    assert error.diagnostics.status == "insufficient_income"
    assert error.diagnostics.iterations > 0
    assert (error.state.pop_wealth[error.state.pops > 0] < 3).any()
    assert error.state.pop_income is not None
    assert error.state.pop_expenses is not None
    untaxed = _with_policy(error.state, False)
    np.testing.assert_allclose(error.state.pop_income, model.pop_income(untaxed))
    np.testing.assert_array_equal(error.state.pop_income_tax, np.zeros((3, 3)))
    assert error.state.pop_buy_orders @ error.state.market_prices == pytest.approx(
        error.state.pop_expenses.sum()
    )


@pytest.mark.parametrize("method", ["nominal", "market"])
def test_policy_rejects_non_equilibrium(subsidy_economy: Economy, method: str):
    with pytest.raises(ValueError, match="requires method='equilibrium'"):
        subsidy_economy.solve(
            np.ones(3), method=method, subsidize_operating_losses=True
        )


def test_tax_snapshot_alignment_and_ownership():
    tax = np.array([[2.0]])
    households = PopState(
        np.array([[1]]), np.array([1.0]), np.array([[3.0]]), pop_income_tax=tax
    )
    tax[:] = 100
    np.testing.assert_array_equal(households.pop_income_tax, [[2]])
    np.testing.assert_array_equal(households.pop_income_before_tax, [[5]])
    for invalid in (np.array([1.0]), np.array([[-1.0]]), np.array([[np.inf]])):
        with pytest.raises(ValueError):
            replace(households, pop_income_tax=invalid)
    assert replace(households, pop_income=None).pop_income_before_tax is None
    np.testing.assert_array_equal(
        replace(households, pop_income_tax=None).pop_income_before_tax, [[3]]
    )


def test_optimizer_rejects_unfunded_trials_and_returns_verified_mix(
    subsidy_economy: Economy,
):
    optimizer = EquilibriumOptimizer(subsidy_economy)
    scenario = Scenario(
        objective="average_wealth",
        min_goods_balance=None,
        building_level_caps=(("farm", 1.0), ("factory", 1.0), ("idle", 0.0)),
        employment_cap=16_000,
    )
    problem = optimizer.compile(scenario)
    assert problem.subsidize_operating_losses
    attribute = "subsidize_operating_losses"
    with pytest.raises(FrozenInstanceError):
        setattr(problem, attribute, False)
    search = _Search(problem, 10)
    bad_score = search.trial(np.array([0.0, 1.0, 0.0]))
    assert search.failures == {"insufficient_income": 1}
    assert search.best is None
    assert search.trial(np.array([1.0, 0.0, 0.0])) < bad_score
    assert search.best is not None
    state = optimizer.solve(
        scenario,
        x0=np.array([1.0, 0.0, 0.0]),
        options={"maxiter": 20},
    )
    assert state.context.subsidize_operating_losses
    assert state.pop_income is not None
    np.testing.assert_allclose(state.pop_income, subsidy_economy.pop_income(state))
    recipes = pd.DataFrame(
        np.eye(3)[:, :2], index=subsidy_economy.building_index, columns=["food", "loss"]
    )
    chain_optimizer = SupplyChainEquilibriumOptimizer(subsidy_economy, recipes)
    chain_problem = chain_optimizer.compile(scenario)
    assert chain_problem.subsidize_operating_losses
    assert chain_problem.building_problem.subsidize_operating_losses
    chain_state = chain_optimizer.solve(
        scenario,
        x0=np.array([1.0, 0.0]),
        options={"maxiter": 20},
    )
    assert chain_state.context.subsidize_operating_losses
    assert chain_state.pop_income_tax is not None
    np.testing.assert_allclose(
        chain_state.pop_income_tax, subsidy_economy.pop_income_tax(chain_state)
    )


@pytest.mark.parametrize("invalid_policy", [1, "yes"])
def test_policy_rejects_non_boolean(subsidy_economy: Economy, invalid_policy):
    with pytest.raises(TypeError, match="must be a boolean"):
        subsidy_economy.solve(
            np.ones(3), method="equilibrium", subsidize_operating_losses=invalid_policy
        )
    context = subsidy_economy.solve(np.ones(3)).context
    with pytest.raises(TypeError, match="must be a boolean"):
        replace(context, subsidize_operating_losses="yes")
    problem = EquilibriumOptimizer(subsidy_economy).compile(Scenario(objective="gdp"))
    with pytest.raises(TypeError, match="must be a boolean"):
        replace(problem, subsidize_operating_losses="yes")


@pytest.mark.parametrize("sign", [-1.0, 1.0])
def test_aggregate_financing_overflow_is_rejected(
    subsidy_economy: Economy, sign: float
):
    state = subsidy_economy.solve(np.ones(3))
    context = replace(
        state.context,
        building_goods_flow=np.array([[sign * 1e308, 0], [sign * 1e308, 0], [0, 0]]),
        subsidize_operating_losses=True,
    )
    state = replace(state, context=context, market=MarketState(context, np.ones(2)))
    with pytest.raises(ValueError, match="Aggregate operating losses and income"):
        subsidy_economy.pop_income(state)


@pytest.mark.parametrize(
    "method, expected", [("nominal", False), ("market", False), ("equilibrium", True)]
)
def test_solver_resolves_default_policy_by_method(
    subsidy_economy: Economy, method: str, expected: bool
):
    levels = np.array([1.0, 0.2, 0.0])
    default = subsidy_economy.solve(levels, method=method, workforce_ratio=0.5)
    explicit_auto = subsidy_economy.solve(
        levels, method=method, workforce_ratio=0.5, subsidize_operating_losses=None
    )
    assert default.context.subsidize_operating_losses is expected
    assert explicit_auto.context.subsidize_operating_losses is expected
    np.testing.assert_array_equal(default.market_prices, explicit_auto.market_prices)
    if expected:
        assert default.pop_income_tax is not None
        assert default.pop_income_tax.sum() > 0
        np.testing.assert_array_equal(
            default.pop_income_tax, explicit_auto.pop_income_tax
        )


@pytest.mark.parametrize("chains", [False, True])
def test_optimizer_recovers_from_unfundable_start(
    subsidy_economy: Economy, chains: bool
):
    scenario = Scenario(
        objective="average_wealth",
        min_goods_balance=None,
        building_level_caps=(("farm", 1.0), ("factory", 1.0), ("idle", 0.0)),
        employment_cap=16_000,
        workforce_ratio=0.5,
    )
    if chains:
        recipes = pd.DataFrame(
            np.eye(3)[:, :2],
            index=subsidy_economy.building_index,
            columns=["food", "loss"],
        )
        optimizer = SupplyChainEquilibriumOptimizer(subsidy_economy, recipes)
        initial = np.array([0.0, 1.0])
    else:
        optimizer = EquilibriumOptimizer(subsidy_economy)
        initial = np.array([0.0, 1.0, 0.0])
    state = optimizer.solve(scenario, x0=initial, options={"maxiter": 100})
    result = optimizer.result
    assert result is not None
    assert 1 < result.nfev <= 100
    assert result.equilibrium_failures["insufficient_income"] > 0
    assert state.equilibrium_diagnostics is not None
    assert state.equilibrium_diagnostics.status == "converged"
    assert state.pop_income_tax is not None
    assert state.pop_income_tax.sum() == pytest.approx(state.building_deficit.sum())
    assert state.total_employment > 0


def test_funding_penalty_guides_search_without_accepting_failed_states(
    subsidy_economy: Economy,
):
    problem = EquilibriumOptimizer(subsidy_economy).compile(
        Scenario(
            objective="average_wealth",
            min_goods_balance=None,
            workforce_ratio=0.5,
        )
    )
    search = _Search(problem, 5)
    worst = search.trial(np.array([0.0, 1.0, 0.0]))
    closer = search.trial(np.array([0.1, 1.0, 0.0]))
    assert np.pi / 2 < closer < worst < np.pi
    assert search.best is None
    assert search.nfev == 2
    assert search.trial(np.array([0.1, 1.0, 0.0])) == closer
    assert search.nfev == 2
    funded = search.trial(np.array([1.0, 0.0, 0.0]))
    assert funded < np.pi / 2
    assert search.best is not None
    assert search.failures == {"insufficient_income": 2}
