"""Declarative optimization scenarios for Victoria 3 economies."""

from dataclasses import dataclass

_OBJECTIVES = (
    "gdp",
    "gdp_per_capita",
    "employment",
    "automation",
    "construction_cost",
)


@dataclass(frozen=True)
class Scenario:
    """An immutable optimization recipe expressed as data.

    The optimizer interpreting a scenario owns all economy-dependent
    compilation. This object only records assumptions shared by the nominal
    and market formulations.
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
        """Validate values that are independent of an economy or optimizer."""
        if self.objective not in _OBJECTIVES:
            raise ValueError(f"Unknown objective: {self.objective!r}")

    def display_name(self) -> str:
        """Return the explicit name or one derived from the produce basket."""
        if self.name is not None:
            return self.name
        if self.produce:
            return "+".join(good for good, _amount in self.produce)
        return "unnamed"
