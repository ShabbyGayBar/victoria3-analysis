"""
Scenario formulation for nominal Victoria 3 linear programmes.

Defines `Scenario`, a frozen dataclass that captures an optimisation
recipe (objective, production basket, import policy, banned production methods
/ buildings, throughput bonuses, caps) as data, and translates it — via pure,
economy-parameterised methods — into the objective vector and constraint
matrices consumed by `NominalOptimizer`.

The translation is deterministic and side-effect free: the constraint order is
fixed (inequality: import cap, construction-cost cap, employment cap, produce
basket, building limits, arable-land cap, infrastructure floor; equality: era
cap, banned PMs, banned building groups, urban-center tie), so duals can be
mapped back to their meaning without inspecting solver internals.  Because the
objective vector and constraints are derived in one pass from the scenario
fields, throughput bonuses are reflected everywhere consistently (no
call-ordering traps).
"""

import re
from dataclasses import dataclass
from typing import TypedDict

import numpy as np
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy

_OBJECTIVES = (
    "gdp",
    "gdp_per_capita",
    "employment",
    "automation",
    "construction_cost",
)


class LinprogArgs(TypedDict):
    """Keyword arguments for `scipy.optimize.linprog`.

    Attributes:
        c: The objective vector to minimise, of shape ``(n_buildings,)``.
        A_ub: Inequality-constraint matrix, or ``None`` when absent.
        b_ub: Inequality-constraint bounds, or ``None`` when absent.
        A_eq: Equality-constraint matrix, or ``None`` when absent.
        b_eq: Equality-constraint bounds, or ``None`` when absent.
    """

    c: np.ndarray
    A_ub: np.ndarray | None
    b_ub: np.ndarray | None
    A_eq: np.ndarray | None
    b_eq: np.ndarray | None


def _stack(
    constraints: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Stack ``(A, b)`` constraint pairs into linprog-ready arrays.

    Args:
        constraints: List of ``(A, b)`` pairs; each ``A`` may be 1-D (a single
            row) or 2-D.

    Returns:
        ``(None, None)`` when *constraints* is empty, otherwise the
        vertically-stacked ``A`` of shape ``(n_rows, n_buildings)`` and the
        horizontally-stacked ``b`` of shape ``(n_rows,)``.
    """
    if not constraints:
        return None, None
    A = np.vstack([a for a, _b in constraints])
    b = np.hstack([b for _a, b in constraints])
    return A, b


@dataclass(frozen=True)
class Scenario:
    """An optimisation recipe expressed as data.

    Captures the knobs varied by the "cangshulun" experiment scripts (terminal
    good, objective, autarky, banned production methods and buildings,
    throughput bonuses, era cap) — generalised to multi-good production
    baskets, arbitrary import caps, per-building level limits, group bans, and
    an infrastructure floor — so a supply-chain optimisation can be re-used and
    compared without re-writing constraint plumbing.

    The translation methods are pure functions of ``(self, economy)``: nothing
    is mutated, results are recomputed on each call, and the constraint order
    is fixed (see `inequality_constraints` and
    `equality_constraints`).

    Attributes:
        produce: Sequence of ``(good_key, amount)`` pairs; each good must be
            produced with at least *amount* net output per week.  Empty means
            no production requirement.
        objective: Named objective. One of ``"gdp"`` (maximise gross GDP),
            ``"gdp_per_capita"`` (maximise GDP per employed person with
            `MarketOptimizer`), ``"employment"`` (maximise total employment), ``"automation"``
            (minimise total employment, i.e. maximise automation) or
            ``"construction_cost"`` (minimise total construction cost).
        import_limit: Maximum net import allowed per good; ``0.0`` (the
            default) enforces autarky and ``None`` disables the constraint.
        banned_pms: Production-method identifiers banned (matched as whole
            words against the concatenated PM string of each configuration).
        building_limits: Sequence of ``(building_key, limit)`` pairs capping
            the combined level of each building's configurations; a limit of
            ``0`` bans the building outright.
        banned_building_groups: Building-group identifiers banned (e.g.
            ``"bg_mining"``).
        throughput_bonuses: Sequence of ``(building_key, multiplier)`` pairs
            scaling the goods flows of every configuration of the building
            (e.g. ``2.45`` for a +145% throughput bonus).  Employment and
            construction cost are not affected.  Bonuses on the same building
            accumulate multiplicatively.
        era_cap: If not ``None``, only configurations with ``era <= era_cap``
            may have non-zero levels.
        construction_cost_cap: If not ``None``, cap total construction cost.
        employment_cap: If not ``None``, cap total employment.
        arable_land_cap: If not ``None``, cap total arable land consumed by
            agricultural, plantation, ranching, and subsistence buildings.
        min_infrastructure: If not ``None``, require total net infrastructure
            (per-configuration ``"infrastructure_usage_per_level"`` column
            summed over building levels) to be at least this value.
        urbanization_per_center: If not ``None``, tie Urban Center levels to
            generated urbanization: every *urbanization_per_center* units of
            urbanization correspond to one ``building_urban_center`` level
            (vanilla uses ``100``).
        name: Optional display name; defaults to the joined produce-basket
            goods when ``None``.
        imports: Fixed imported goods as ``(good_key, amount)`` pairs.
        exports: Fixed exported goods as ``(good_key, amount)`` pairs.
        pop_needs: Fixed population-needs demand as ``(good_key, amount)``
            pairs.
    """

    produce: tuple[tuple[str, float], ...] = ()
    objective: str = "automation"
    import_limit: float | None = 0.0
    banned_pms: tuple[str, ...] = ()
    building_limits: tuple[tuple[str, float], ...] = ()
    banned_building_groups: tuple[str, ...] = ()
    throughput_bonuses: tuple[tuple[str, float], ...] = ()
    era_cap: int | None = None
    construction_cost_cap: float | None = None
    employment_cap: float | None = None
    arable_land_cap: float | None = None
    min_infrastructure: float | None = None
    urbanization_per_center: float | None = None
    name: str | None = None
    imports: tuple[tuple[str, float], ...] = ()
    exports: tuple[tuple[str, float], ...] = ()
    pop_needs: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        """Validate the objective name at construction time.

        Raises:
            ValueError: If `objective` is not one of the named
                objectives.
        """
        if self.objective not in _OBJECTIVES:
            raise ValueError(f"Unknown objective: {self.objective!r}")

    def display_name(self) -> str:
        """Return the scenario name, falling back to the produce basket.

        Returns:
            `name` if set, otherwise the produce-basket good keys joined
            with ``"+"``, or ``"unnamed"`` when the basket is empty.
        """
        if self.name is not None:
            return self.name
        if self.produce:
            return "+".join(good for good, _amount in self.produce)
        return "unnamed"

    def _goods_context_vector(
        self, economy: Economy, entries: tuple[tuple[str, float], ...], name: str
    ) -> np.ndarray:
        """Translate named fixed market context into a goods-aligned vector."""
        goods_index = economy.goods_index()
        positions = {good: i for i, good in enumerate(goods_index)}
        vector = np.zeros(len(goods_index), dtype=np.float64)
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ValueError(f"{name} entries must be (good, amount) pairs.")
            good, amount = entry
            if not isinstance(good, str):
                raise ValueError(f"{name} good keys must be strings.")
            if good not in positions:
                raise ValueError(
                    f"Good '{good}' in {name} was not found in goods index."
                )
            try:
                value = float(amount)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{name} amounts must be finite non-negative numbers."
                ) from exc
            if not np.isfinite(value) or value < 0:
                raise ValueError(
                    f"{name} amounts must be finite non-negative numbers."
                )
            position = positions[good]
            if value > np.finfo(np.float64).max - vector[position]:
                raise ValueError(f"{name} totals must remain finite.")
            vector[position] += value
        return vector

    def imports_vector(self, economy: Economy) -> np.ndarray:
        """Return fixed imports aligned to ``economy.goods_index()``."""
        return self._goods_context_vector(economy, self.imports, "imports")

    def exports_vector(self, economy: Economy) -> np.ndarray:
        """Return fixed exports aligned to ``economy.goods_index()``."""
        return self._goods_context_vector(economy, self.exports, "exports")

    def pop_needs_vector(self, economy: Economy) -> np.ndarray:
        """Return fixed population needs aligned to ``economy.goods_index()``."""
        return self._goods_context_vector(economy, self.pop_needs, "pop_needs")

    def throughput_multipliers(self, economy: Economy) -> np.ndarray:
        """Return per-configuration goods-flow multipliers from bonuses.

        Args:
            economy: The `Economy` whose production table is scaled.

        Returns:
            A 1-D array of shape ``(n_buildings,)`` where each entry is the
            product of all bonus multipliers matching that configuration's
            building (``1.0`` where no bonus applies).
        """
        multipliers = np.ones(len(economy.df_production), dtype=np.float64)
        buildings = economy.df_production["building"].to_numpy()
        for building_key, multiplier in self.throughput_bonuses:
            multipliers[buildings == building_key] *= multiplier
        return multipliers

    def goods_input_matrix(self, economy: Economy) -> np.ndarray:
        """Return the throughput-adjusted goods input matrix.

        Args:
            economy: The `Economy` whose production table is scaled.

        Returns:
            The ``(n_buildings, n_goods)`` input matrix with the rows of
            bonused buildings scaled by their multipliers.
        """
        return economy.goods_input_matrix(
            throughput_multipliers=self.throughput_multipliers(economy)
        )

    def goods_output_matrix(self, economy: Economy) -> np.ndarray:
        """Return the throughput-adjusted goods output matrix.

        Args:
            economy: The `Economy` whose production table is scaled.

        Returns:
            The ``(n_buildings, n_goods)`` output matrix with the rows of
            bonused buildings scaled by their multipliers.
        """
        return economy.goods_output_matrix(
            throughput_multipliers=self.throughput_multipliers(economy)
        )

    def goods_matrix(self, economy: Economy) -> np.ndarray:
        """Return the throughput-adjusted net goods matrix (output - input).

        Args:
            economy: The `Economy` whose production table is scaled.

        Returns:
            The ``(n_buildings, n_goods)`` net goods matrix reflecting
            throughput bonuses.
        """
        return self.goods_output_matrix(economy) - self.goods_input_matrix(economy)

    def gdp_vector(self, economy: Economy) -> np.ndarray:
        """Return gross-GDP value per building level at base prices.

        Args:
            economy: The `Economy` providing prices and flows.

        Returns:
            A 1-D array of shape ``(n_buildings,)`` computed as
            ``goods_matrix(economy) @ economy.base_prices()``.
        """
        return self.goods_matrix(economy) @ economy.base_prices()

    def objective_vector(self, economy: Economy) -> np.ndarray:
        """Return the linprog ``c`` vector to minimise for the objective.

        ``scipy.optimize.linprog`` minimises, so maximisation objectives are
        negated.

        Args:
            economy: The `Economy` providing the derived vectors.

        Returns:
            The objective vector of shape ``(n_buildings,)``.

        Raises:
            ValueError: If `objective` is not recognised (only possible
                when the dataclass was constructed bypassing validation).
        """
        if self.objective == "gdp":
            return -self.gdp_vector(economy)
        if self.objective == "gdp_per_capita":
            raise ValueError(
                "gdp_per_capita is nonlinear and requires MarketOptimizer."
            )
        if self.objective == "employment":
            return -economy.employment_vector()
        if self.objective == "automation":
            return economy.employment_vector()
        if self.objective == "construction_cost":
            return economy.construction_cost_vector()
        raise ValueError(f"Unknown objective: {self.objective!r}")

    def inequality_constraints(
        self, economy: Economy
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Return the stacked inequality constraints ready for ``linprog``.

        Rows follow a fixed order — import cap, construction-cost cap,
        employment cap, produce basket, building level limits, arable-land cap,
        infrastructure floor — with the import block leading whenever present, so
        `import_marginals` can slice its duals directly.

        Args:
            economy: The `Economy` providing the derived vectors.

        Returns:
            A ``(A_ub, b_ub)`` tuple enforcing ``A_ub @ x <= b_ub``, of shapes
            ``(n_rows, n_buildings)`` and ``(n_rows,)``, or ``(None, None)``
            when the scenario has no inequality constraints.

        Raises:
            ValueError: If a `produce` good is not in the goods index.
        """
        return _stack(self._inequality_pairs(economy))

    def equality_constraints(
        self, economy: Economy
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Return the stacked equality constraints ready for ``linprog``.

        Rows follow a fixed order — era cap, banned PMs, banned building
        groups, urban-center tie.

        Args:
            economy: The `Economy` providing the production table.

        Returns:
            A ``(A_eq, b_eq)`` tuple enforcing ``A_eq @ x == b_eq``, of shapes
            ``(n_rows, n_buildings)`` and ``(n_rows,)``, or ``(None, None)``
            when the scenario has no equality constraints.
        """
        return _stack(self._equality_pairs(economy))

    def linprog_args(self, economy: Economy) -> LinprogArgs:
        """Return keyword arguments ready for `scipy.optimize.linprog`.

        Bundles `objective_vector`, `inequality_constraints`, and
        `equality_constraints` so the LP can be invoked directly::

            opt.linprog(**scenario.linprog_args(economy))

        Args:
            economy: The `Economy` providing the derived vectors.

        Returns:
            A `LinprogArgs` ``TypedDict`` (a plain ``dict`` at runtime)
            with keys ``"c"``, ``"A_ub"``, ``"b_ub"``, ``"A_eq"`` and
            ``"b_eq"``; constraint entries are ``None`` when the scenario has
            no such constraints.

        Raises:
            ValueError: If a `produce` good is not in the goods index.
        """
        A_ub, b_ub = self.inequality_constraints(economy)
        A_eq, b_eq = self.equality_constraints(economy)
        return {
            "c": self.objective_vector(economy),
            "A_ub": A_ub,
            "b_ub": b_ub,
            "A_eq": A_eq,
            "b_eq": b_eq,
        }

    def _inequality_pairs(
        self, economy: Economy
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Build the inequality ``(A, b)`` blocks in the documented order."""
        constraints: list[tuple[np.ndarray, np.ndarray]] = []
        goods_matrix = self.goods_matrix(economy)
        if self.import_limit is not None:
            constraints.append(
                (
                    -goods_matrix.T,
                    np.full(goods_matrix.shape[1], self.import_limit),
                )
            )
        if self.construction_cost_cap is not None:
            constraints.append(
                (
                    economy.construction_cost_vector(),
                    np.array([self.construction_cost_cap]),
                )
            )
        if self.employment_cap is not None:
            constraints.append(
                (economy.employment_vector(), np.array([self.employment_cap]))
            )
        if self.produce:
            goods_index = economy.goods_index()
            rows = []
            amounts = []
            for good, amount in self.produce:
                if good not in goods_index:
                    raise ValueError(f"Good '{good}' not found in goods index.")
                rows.append(-goods_matrix[:, goods_index.index(good)])
                amounts.append(-amount)
            constraints.append((np.vstack(rows), np.array(amounts)))
        if self.building_limits:
            buildings = economy.df_production["building"].to_numpy()
            rows = [
                (buildings == building_key).astype(np.float64)
                for building_key, _limit in self.building_limits
            ]
            limits = [limit for _building_key, limit in self.building_limits]
            constraints.append((np.vstack(rows), np.array(limits, dtype=np.float64)))
        if self.arable_land_cap is not None:
            constraints.append(
                (economy.arable_land_vector(), np.array([self.arable_land_cap]))
            )
        if self.min_infrastructure is not None:
            infrastructure = (
                economy.df_production["infrastructure_usage_per_level"]
                .fillna(0)
                .to_numpy(dtype=np.float64)
            )
            constraints.append((-infrastructure, np.array([-self.min_infrastructure])))
        return constraints

    def _equality_pairs(self, economy: Economy) -> list[tuple[np.ndarray, np.ndarray]]:
        """Build the equality ``(A, b)`` blocks in the documented order."""
        constraints: list[tuple[np.ndarray, np.ndarray]] = []
        if self.era_cap is not None:
            mask = (economy.df_production["era"] > self.era_cap).to_numpy()
            constraints.append((mask.astype(np.float64), np.array([0.0])))
        if self.banned_pms:
            pattern = re.compile(
                r"\b(?:" + "|".join(re.escape(k) for k in self.banned_pms) + r")\b"
            )
            mask = (
                economy.df_production["production_method"]
                .str.contains(pattern, na=False)
                .to_numpy()
            )
            constraints.append((mask.astype(np.float64), np.array([0.0])))
        if self.banned_building_groups:
            rows = [
                (economy.df_production["building_group"] == building_group)
                .to_numpy()
                .astype(np.float64)
                for building_group in self.banned_building_groups
            ]
            constraints.append((np.vstack(rows), np.zeros(len(rows))))
        if self.urbanization_per_center is not None:
            urbanization = (
                economy.df_production["urbanization"]
                .fillna(0)
                .to_numpy(dtype=np.float64)
            )
            urban_center = (
                economy.df_production["building"] == "building_urban_center"
            ).to_numpy()
            constraints.append(
                (
                    urbanization - self.urbanization_per_center * urban_center,
                    np.array([0.0]),
                )
            )
        return constraints

    def import_marginals(
        self, economy: Economy, result: OptimizeResult | None
    ) -> np.ndarray | None:
        """Return the import-cap shadow prices from a solved LP result.

        The import block is the first inequality block (see
        `inequality_constraints`), so its marginals are the leading
        ``n_goods`` entries of the inequality marginals.

        Args:
            economy: The `Economy` the scenario was solved on.
            result: The `scipy.optimize.OptimizeResult` stored by
                `NominalOptimizer.solve`, or ``None``.

        Returns:
            Import-cap marginal values of length ``n_goods``, or ``None`` when
            unavailable (no import constraint, no solved result, or the result
            lacks marginals).
        """
        if self.import_limit is None or result is None:
            return None
        ineqlin = getattr(result, "ineqlin", None)
        if ineqlin is None:
            return None
        marginals = getattr(ineqlin, "marginals", None)
        if marginals is None:
            return None
        marginals_arr = np.asarray(marginals, dtype=np.float64)
        n_goods = len(economy.goods_index())
        if marginals_arr.shape[0] < n_goods:
            return None
        return marginals_arr[:n_goods]
