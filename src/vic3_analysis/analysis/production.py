"""
Production-table analysis for Victoria 3.

Builds the production table: one row per building configuration (a building
combined with one production method per production-method group), derived
purely from the four pre-generated parse tables (buildings, goods,
production methods, and technology).
"""

import warnings
from itertools import product

import numpy as np
import pandas as pd


def _tech_keys(value: object) -> list[str]:
    """Split a ``+``-joined unlocking-technologies value into tech keys.

    Args:
        value: A raw ``unlocking_technologies`` column value.  Values are
            ``+``-joined technology keys; missing values (``NaN``) have none.

    Returns:
        The list of technology keys, empty when the value is missing or empty.
    """
    if not isinstance(value, str):
        return []
    return [key for key in value.split("+") if key]


def _era_of_techs(tech_keys: list[str], era_by_tech: dict[str, int]) -> int:
    """Return the maximum era among the given unlocking technologies.

    Args:
        tech_keys: Unlocking technology keys (may be empty).
        era_by_tech: Mapping of technology key to era.

    Returns:
        The maximum era, or ``0`` when no technologies are given.

    Raises:
        ValueError: If a technology key is missing from ``era_by_tech``.
    """
    era = 0
    for key in tech_keys:
        if key not in era_by_tech:
            raise ValueError(f"Unknown unlocking technology: {key}")
        era = max(era, era_by_tech[key])
    return era


def production_table(
    df_buildings: pd.DataFrame,
    df_goods: pd.DataFrame,
    df_pm: pd.DataFrame,
    df_tech: pd.DataFrame,
) -> pd.DataFrame:
    """Build the production table of all building configurations.

    For every building, enumerates every combination of production methods
    (one per production-method group) and aggregates the per-method
    employment (total and per profession) and net goods flows (positive =
    output, negative = input).  The ``infrastructure_usage_per_level``
    column holds the net per-level footprint: the building group's usage
    minus the ``state_infrastructure_add`` generation summed over the chosen
    production methods, so provider configurations (ports, railways, urban
    centers) carry negative values under the full-employment nominal model.
    Buildings without a construction cost are
    kept with a construction cost of ``0``.  Each row also records the
    technologies required to unlock the configuration (the building's own
    unlocking technologies followed by those of every chosen production
    method, de-duplicated in order of first appearance) and the earliest era
    at which the configuration becomes available (the maximum era of those
    technologies, ``0`` when none).  Nominal values are evaluated at the
    goods table's base prices; the ratio columns follow plain division
    semantics (``x / 0`` is ``inf`` and ``0 / 0`` is ``NaN``).

    Args:
        df_buildings: Buildings table (``BuildingsParser.to_dataframe()`` or
            ``tables/buildings.csv``) with ``key``, ``building_group``,
            ``urbanization``, ``infrastructure_usage_per_level``,
            ``required_construction_points``, ``production_method_groups``,
            and ``unlocking_technologies`` columns.
        df_goods: Goods table (:func:`~vic3_analysis.goods` or
            ``tables/goods.csv``) with ``key`` and ``cost`` columns.  Its row
            order fixes the ``goods_<good>`` column order of the result.
        df_pm: Production-methods table
            (``ProductionMethodParser.to_dataframe()`` or
            ``tables/production_methods.csv``) with ``building``,
            ``production_method_group``, ``production_method``,
            ``unlocking_technologies``, ``employment``,
            ``employment_<profession>``, ``state_infrastructure_add``, and
            ``goods_<good>`` columns (the state-infrastructure column is
            zero-filled with a warning when absent).
        df_tech: Technology table (:func:`~vic3_analysis.technology` or
            ``tables/technology.csv``) with ``key`` and ``era`` columns.

    Returns:
        A ``DataFrame`` with one row per building configuration.  The
        ``"production_method"`` column holds the chosen production methods
        concatenated with ``+``.  The remaining columns are ``"building"``,
        ``"building_group"``, ``"urbanization"``,
        ``"infrastructure_usage_per_level"`` (net of the configuration's
        ``state_infrastructure_add`` generation), ``"era"``,
        ``"unlocking_tech"``, ``"employment"``, ``"construction_cost"``,
        ``"value_goods_inputs_nominal"``, ``"value_goods_outputs_nominal"``,
        ``"profit_nominal"``, ``"profit_margin_nominal"``,
        ``"profit_per_capita_nominal"``, and
        ``"profit_per_construction_cost_nominal"``, followed by one
        ``goods_<good>`` column per good and one ``employment_<profession>``
        column per profession.

    Raises:
        ValueError: If an unlocking technology referenced by a building or a
            production method is missing from the technology table.
    """
    goods_cols = [f"goods_{key}" for key in df_goods["key"]]
    profession_cols = [col for col in df_pm.columns if col.startswith("employment_")]
    sum_cols = ["employment", *profession_cols, "state_infrastructure_add", *goods_cols]

    missing_goods_cols = [col for col in goods_cols if col not in df_pm.columns]
    if missing_goods_cols:
        warnings.warn(
            f"Goods columns missing from the production-method table, "
            f"zero-filled: {sorted(missing_goods_cols)}",
            stacklevel=2,
        )
        df_pm = df_pm.reindex(
            columns=[*df_pm.columns, *missing_goods_cols], fill_value=0
        )
    if "state_infrastructure_add" not in df_pm.columns:
        warnings.warn(
            "State-infrastructure column missing from the production-method "
            "table, zero-filled: state_infrastructure_add",
            stacklevel=2,
        )
        df_pm = df_pm.reindex(
            columns=[*df_pm.columns, "state_infrastructure_add"], fill_value=0
        )
    unpriced_goods_cols = [
        col
        for col in df_pm.columns
        if col.startswith("goods_") and col not in goods_cols
    ]
    if unpriced_goods_cols:
        warnings.warn(
            f"Goods columns without a base price, ignored: "
            f"{sorted(unpriced_goods_cols)}",
            stacklevel=2,
        )

    era_by_tech: dict[str, int] = {
        key: int(era) for key, era in zip(df_tech["key"], df_tech["era"])
    }

    pm_keys = df_pm["production_method"].tolist()
    pm_techs = [_tech_keys(value) for value in df_pm["unlocking_technologies"]]
    pm_eras = [_era_of_techs(techs, era_by_tech) for techs in pm_techs]

    group_positions: dict[tuple[str, str], list[int]] = {}
    for position, (building, group) in enumerate(
        zip(df_pm["building"], df_pm["production_method_group"])
    ):
        group_positions.setdefault((building, group), []).append(position)

    building_columns = [
        "key",
        "building_group",
        "urbanization",
        "infrastructure_usage_per_level",
        "required_construction_points",
        "production_method_groups",
        "unlocking_technologies",
    ]
    combo_rows: list[dict[str, object]] = []
    membership: list[tuple[int, int]] = []

    for (
        building,
        building_group,
        urbanization,
        infrastructure,
        construction_cost,
        pmg_value,
        unlock_value,
    ) in zip(*[df_buildings[column] for column in building_columns]):
        if not isinstance(pmg_value, str) or not pmg_value:
            warnings.warn(
                f"Building {building} has no production method groups, skipped",
                stacklevel=2,
            )
            continue

        groups: list[list[int]] = []
        for pmg in pmg_value.split("+"):
            positions = group_positions.get((building, pmg))
            if not positions:
                warnings.warn(
                    f"Building {building} has no production methods in group "
                    f"{pmg}, skipped",
                    stacklevel=2,
                )
                groups = []
                break
            groups.append(positions)
        if not groups:
            continue

        building_techs = _tech_keys(unlock_value)
        building_era = _era_of_techs(building_techs, era_by_tech)
        if pd.isna(construction_cost):
            construction_cost = 0
        if pd.isna(urbanization):
            urbanization = 0.0
        if pd.isna(infrastructure):
            infrastructure = 0.0

        for positions in product(*groups):
            combo_id = len(combo_rows)
            era = building_era
            techs = list(building_techs)
            for position in positions:
                if pm_eras[position] > era:
                    era = pm_eras[position]
                techs.extend(pm_techs[position])
            combo_rows.append(
                {
                    "building": building,
                    "production_method": "+".join(
                        pm_keys[position] for position in positions
                    ),
                    "building_group": building_group,
                    "urbanization": urbanization,
                    "infrastructure_usage_per_level": infrastructure,
                    "era": era,
                    "unlocking_tech": "+".join(dict.fromkeys(techs)),
                    "construction_cost": int(construction_cost),
                }
            )
            membership.extend((combo_id, position) for position in positions)

    column_order = [
        "building",
        "production_method",
        "building_group",
        "urbanization",
        "infrastructure_usage_per_level",
        "era",
        "unlocking_tech",
        "employment",
        "construction_cost",
        "value_goods_inputs_nominal",
        "value_goods_outputs_nominal",
        "profit_nominal",
        "profit_margin_nominal",
        "profit_per_capita_nominal",
        "profit_per_construction_cost_nominal",
        *goods_cols,
        *profession_cols,
    ]
    if not combo_rows:
        return pd.DataFrame(columns=column_order)

    member_positions = [position for _, position in membership]
    combo_ids = [combo_id for combo_id, _ in membership]
    members = df_pm.iloc[member_positions]
    sums = (
        members.groupby(np.asarray(combo_ids), sort=True)[sum_cols]
        .sum()
        .reset_index(drop=True)
    )

    result = pd.concat([pd.DataFrame(combo_rows), sums], axis=1)

    result["infrastructure_usage_per_level"] = (
        result["infrastructure_usage_per_level"] - result["state_infrastructure_add"]
    )

    prices = df_goods["cost"].to_numpy(dtype=np.float64)
    flows = result[goods_cols].to_numpy(dtype=np.float64)
    result["value_goods_inputs_nominal"] = np.maximum(-flows, 0.0) @ prices
    result["value_goods_outputs_nominal"] = np.maximum(flows, 0.0) @ prices
    result["profit_nominal"] = (
        result["value_goods_outputs_nominal"] - result["value_goods_inputs_nominal"]
    )
    result["profit_margin_nominal"] = (
        result["profit_nominal"] / result["value_goods_outputs_nominal"]
    )
    result["profit_per_capita_nominal"] = (
        result["profit_nominal"] / result["employment"]
    )
    result["profit_per_construction_cost_nominal"] = (
        result["profit_nominal"] / result["construction_cost"]
    )

    return result.reindex(columns=column_order)
