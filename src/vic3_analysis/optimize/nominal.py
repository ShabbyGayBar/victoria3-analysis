"""
Nominal linear-programming optimiser for Victoria 3 economies.

Builds on :class:`~vic3_analysis.analysis.economy.Economy` to optimise
building levels for a named objective (gross GDP, employment, or construction
cost) subject to inequality/equality constraints, via
:func:`scipy.optimize.linprog`.
"""

import re
from typing import List, Self, Tuple

import numpy as np
import scipy.optimize as opt
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState


class NominalOptimizer:
    """Linear-programming optimiser over an :class:`Economy`.

    Wraps an :class:`Economy` and provides constraint builders and a
    :meth:`linprog` solver.

    The objective vector and constraint lists are stored as instance attributes
    and populated at construction (via *objective* and the constraint lists) or
    incrementally via the fluent ``constraint_*`` and :meth:`set_objective`
    builders, which return ``self`` so calls can be chained::

        state = (
            NominalOptimizer(model)
            .set_objective("gdp")
            .constraint_limit_construction_cost(5000)
            .constraint_limit_import(0.0)
            .linprog()
        )

    Attributes:
        model: The wrapped :class:`Economy`.
        objective_vector: The ``c`` vector to minimise, of shape
            ``(n_buildings,)``, set by :meth:`set_objective`.
        inequality_constraints: List of ``(A, b)`` pairs representing
            ``A @ x <= b`` constraints.
        equality_constraints: List of ``(A, b)`` pairs representing
            ``A @ x == b`` constraints.
        result: The :class:`scipy.optimize.OptimizeResult` from the most
            recent :meth:`linprog` call (``None`` until solved).  Exposed so
            downstream tooling can read constraint marginals (shadow prices);
            callers should not mutate it.
    """

    model: Economy
    objective_vector: np.ndarray
    inequality_constraints: List[Tuple[np.ndarray, np.ndarray]]
    equality_constraints: List[Tuple[np.ndarray, np.ndarray]]
    goods_matrix: np.ndarray
    result: OptimizeResult | None

    def __init__(
        self,
        model: Economy,
        objective: str = "gdp",
        inequality_constraints: List[Tuple[np.ndarray, np.ndarray]] | None = None,
        equality_constraints: List[Tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> None:
        """Initialise the optimiser.

        Args:
            model: The :class:`Economy` to optimise over.
            objective: Named objective used to seed :attr:`objective_vector`
                via :meth:`set_objective`.  One of ``"gdp"``,
                ``"employment"``, ``"automation"`` or ``"construction_cost"``.
            inequality_constraints: Optional initial list of ``(A, b)``
                inequality pairs.  Copied defensively.
            equality_constraints: Optional initial list of ``(A, b)``
                equality pairs.  Copied defensively.
        """
        self.model = model
        self.reset(objective, inequality_constraints, equality_constraints)

    def reset(
        self,
        objective: str = "gdp",
        inequality_constraints: List[Tuple[np.ndarray, np.ndarray]] | None = None,
        equality_constraints: List[Tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> Self:
        """Reset the optimiser to a clean state.

        Args:
            objective: Named objective used to seed :attr:`objective_vector`
                via :meth:`set_objective`.  One of ``"gdp"``,
                ``"employment"``, ``"automation"`` or ``"construction_cost"``.
            inequality_constraints: Optional initial list of ``(A, b)``
                inequality pairs.  Copied defensively.
            equality_constraints: Optional initial list of ``(A, b)``
                equality pairs.  Copied defensively.

        Returns:
            ``self``, for fluent chaining.
        """
        self.goods_matrix = (
            self.model.goods_output_matrix() - self.model.goods_input_matrix()
        )
        self.set_objective(objective)
        self.inequality_constraints = (
            list(inequality_constraints) if inequality_constraints else []
        )
        self.equality_constraints = (
            list(equality_constraints) if equality_constraints else []
        )
        self.result = None
        return self

    def base_prices(self) -> np.ndarray:
        """Base (nominal) goods prices of shape ``(n_goods,)``."""
        return self.model.base_prices()

    def gdp_vector(self) -> np.ndarray:
        """Gross-GDP value per building level of shape ``(n_buildings,)``.

        Computed as ``goods_matrix @ base_prices()`` (i.e. levels @ net
        supply valued at base prices).
        """
        return self.goods_matrix @ self.base_prices()

    def employment_vector(self) -> np.ndarray:
        """Total employment per building level of shape ``(n_buildings,)``."""
        return (
            self.model.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
        )

    def construction_cost_vector(self) -> np.ndarray:
        """Construction cost per building level of shape ``(n_buildings,)``."""
        return self.model.construction_cost_vector()

    def goods_index(self) -> list[str]:
        """Good keys in ``df_goods`` row order."""
        return self.model.goods_index()

    def set_objective(self, objective: str) -> Self:
        """Set :attr:`objective_vector` from a named objective.

        ``scipy.optimize.linprog`` minimises, so maximisation objectives are
        negated.

        Args:
            objective: One of ``"gdp"`` (maximise gross GDP),
                ``"employment"`` (maximise total employment), ``"automation"``
                (minimise total employment, i.e. maximise automation) or
                ``"construction_cost"`` (minimise total construction cost).

        Returns:
            ``self``, for fluent chaining.

        Raises:
            ValueError: If *objective* is not recognised.
        """
        if objective == "gdp":
            self.objective_vector = -self.gdp_vector()
        elif objective == "employment":
            self.objective_vector = -self.employment_vector()
        elif objective == "automation":
            self.objective_vector = self.employment_vector()
        elif objective == "construction_cost":
            self.objective_vector = self.construction_cost_vector()
        else:
            raise ValueError(f"Unknown objective: {objective!r}")
        return self

    def add_throughput_bonus(self, building_key: str, bonus_multiplier: float) -> Self:
        """Apply a throughput bonus to all configurations of a building.

        Scales the goods flows of every configuration whose ``"building"``
        column matches *building_key* in :attr:`goods_matrix` by
        *bonus_multiplier*.  Employment and construction cost are not
        affected.  :attr:`objective_vector` is not refreshed automatically;
        call :meth:`set_objective` afterwards to reflect the bonus.

        Args:
            building_key: The building identifier to bonus (e.g.
                ``"building_textile_mill"``).
            bonus_multiplier: Factor by which to multiply goods flows (e.g.
                ``2.45`` for a +145% throughput bonus).

        Returns:
            ``self``, for fluent chaining.
        """
        mask = (self.model.df_production["building"] == building_key).to_numpy()
        self.goods_matrix[mask, :] *= bonus_multiplier
        return self

    def constraint_limit_import(self, limit: float = 0.0) -> Self:
        """Append an inequality constraint capping net imports of each good.

        Builds a matrix-vector pair ``(A, b)`` such that ``A @ x <= b``
        enforces that the net flow of every good does not exceed *limit*, and
        appends it to :attr:`inequality_constraints`.

        Args:
            limit: Maximum allowable net import per good.  Defaults to ``0.0``
                (no net imports).

        Returns:
            ``self``, for fluent chaining.
        """
        goods_matrix = self.goods_matrix
        A = -goods_matrix.T
        b = np.ones(goods_matrix.shape[1]) * limit
        self.inequality_constraints.append((A, b))
        return self

    def constraint_limit_employment(self, limit: float) -> Self:
        """Append an inequality constraint capping total employment.

        Args:
            limit: Maximum total employment allowed.

        Returns:
            ``self``, for fluent chaining.
        """
        self.inequality_constraints.append(
            (self.employment_vector(), np.array([limit]))
        )
        return self

    def constraint_limit_construction_cost(self, limit: float) -> Self:
        """Append an inequality constraint capping total construction cost.

        Args:
            limit: Maximum total construction cost allowed.

        Returns:
            ``self``, for fluent chaining.
        """
        self.inequality_constraints.append(
            (self.construction_cost_vector(), np.array([limit]))
        )
        return self

    def constraint_limit_building(self, building_key: str, limit: float) -> Self:
        """Append an inequality constraint limiting levels of one building type.

        Args:
            building_key: The building identifier to restrict.
            limit: Maximum combined level for all configurations of this
                building.

        Returns:
            ``self``, for fluent chaining.
        """
        A = np.zeros(len(self.model.df_production))
        mask = (self.model.df_production["building"] == building_key).to_numpy()
        A[mask] = 1
        b = np.array([limit])
        self.inequality_constraints.append((A, b))
        return self

    def constraint_produce(self, good_key: str, limit: float = 1) -> Self:
        """Append an inequality constraint requiring minimum production of a good.

        Args:
            good_key: The good identifier that must be produced.
            limit: Minimum required net production of the good.  Defaults to
                ``1``.

        Returns:
            ``self``, for fluent chaining.

        Raises:
            ValueError: If *good_key* is not present in the goods index.
        """
        goods_index = self.goods_index()
        if good_key not in goods_index:
            raise ValueError(f"Good '{good_key}' not found in goods index.")
        idx = goods_index.index(good_key)
        A = -self.goods_matrix[:, idx]
        b = np.array([-limit])
        self.inequality_constraints.append((A, b))
        return self

    def constraint_ban_building(self, building_keys: List[str]) -> Self:
        """Append an equality constraint forcing banned building levels to zero.

        Every configuration whose ``"building"`` column matches one of
        *building_keys* is forced to level zero via ``A @ x == 0``.

        Args:
            building_keys: Building identifiers to ban (e.g.
                ``"building_iron_mine"``).

        Returns:
            ``self``, for fluent chaining.
        """
        A = np.zeros(len(self.model.df_production))
        mask = self.model.df_production["building"].isin(building_keys).to_numpy()
        A[mask] = 1
        b = np.array([0.0])
        self.equality_constraints.append((A, b))
        return self

    def constraint_ban_pm(self, production_method_keys: List[str]) -> Self:
        """Append an equality constraint forcing banned PM-config levels to zero.

        Every configuration whose ``"production_method"`` column contains any of
        *production_method_keys* (matched as a whole word) is forced to level
        zero via ``A @ x == 0``.

        Args:
            production_method_keys: Production-method identifiers to ban.

        Returns:
            ``self``, for fluent chaining.
        """
        A = np.zeros(len(self.model.df_production))
        if production_method_keys:
            pattern = re.compile(
                r"\b(?:"
                + "|".join(re.escape(k) for k in production_method_keys)
                + r")\b"
            )
            mask = (
                self.model.df_production["production_method"]
                .str.contains(pattern, na=False)
                .to_numpy()
            )
            A[mask] = 1
        b = np.array([0.0])
        self.equality_constraints.append((A, b))
        return self

    def constraint_limit_era(self, era: int) -> Self:
        """Append an equality constraint capping configurations by era.

        Every configuration whose ``"era"`` column is greater than *era* is
        forced to level zero via ``A @ x == 0``.

        Args:
            era: Era threshold; only configurations with ``era <= era`` may have
                non-zero levels.

        Returns:
            ``self``, for fluent chaining.
        """
        A = np.zeros(len(self.model.df_production))
        mask = (self.model.df_production["era"] > era).to_numpy()
        A[mask] = 1
        b = np.array([0.0])
        self.equality_constraints.append((A, b))
        return self

    def constraint_ban_building_group(self, building_group: str) -> Self:
        """Append an equality constraint banning a building group.

        Every configuration whose ``"building_group"`` column matches
        *building_group* is forced to level zero via ``A @ x == 0``.

        Args:
            building_group: The building-group identifier to ban (e.g.
                ``"bg_mining"``).

        Returns:
            ``self``, for fluent chaining.
        """
        A = np.zeros(len(self.model.df_production))
        mask = (self.model.df_production["building_group"] == building_group).to_numpy()
        A[mask] = 1
        b = np.array([0.0])
        self.equality_constraints.append((A, b))
        return self

    def linprog(self) -> EconomyState:
        """Solve a linear programme over building levels.

        Minimises :attr:`objective_vector` subject to
        :attr:`inequality_constraints` (``A @ x <= b``) and
        :attr:`equality_constraints` (``A @ x == b``), where ``x`` is the
        vector of building levels.

        Returns:
            An :class:`EconomyState` (via :meth:`Economy.solve`) built from the
            optimal building-level vector.  The underlying
            :class:`scipy.optimize.OptimizeResult` is also stored on
            :attr:`result` for marginal inspection.

        Raises:
            ValueError: If :func:`scipy.optimize.linprog` reports that the
                optimisation failed.
        """
        A_ub = (
            np.vstack([constraint[0] for constraint in self.inequality_constraints])
            if self.inequality_constraints
            else None
        )
        b_ub = (
            np.hstack([constraint[1] for constraint in self.inequality_constraints])
            if self.inequality_constraints
            else None
        )
        A_eq = (
            np.vstack([constraint[0] for constraint in self.equality_constraints])
            if self.equality_constraints
            else None
        )
        b_eq = (
            np.hstack([constraint[1] for constraint in self.equality_constraints])
            if self.equality_constraints
            else None
        )
        res = opt.linprog(
            c=self.objective_vector,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
        )
        if not res.success:
            raise ValueError(f"Optimization failed: {res.message}")
        self.result = res
        return self.model.solve(res.x)
