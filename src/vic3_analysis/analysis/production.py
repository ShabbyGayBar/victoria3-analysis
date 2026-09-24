"""
Production-table analysis for Victoria 3.

Builds the production table: one row per building configuration (a building
combined with one production method per production-method group), derived
from the buildings, goods, and production-method tables with optional
technology and pop-type enrichment.
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
    df_tech: pd.DataFrame | None = None,
    df_pop_types: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the production table of all building configurations.

    For every building, enumerates every combination of production methods
    (one per production-method group) and aggregates the per-method
    employment (total and per profession) and net goods flows (positive =
    output, negative = input). When pop types are supplied, wage-normalized
    employment is the sum of each profession's employment multiplied by its
    wage weight, restricted to pop types whose ``paid_private_wage`` flag is
    true. The
    ``infrastructure_usage_per_level``
    column holds the net per-level footprint: the building group's usage
    minus the ``state_infrastructure_add`` generation summed over the chosen
    production methods, so provider configurations (ports, railways, urban
    centers) carry negative values under the full-employment nominal model.
    Buildings without a construction cost are
    kept with a construction cost of ``0``.  Each row also records the
    technologies required to unlock the configuration (the building's own
    unlocking technologies followed by those of every chosen production
    method, de-duplicated in order of first appearance). When technology data
    is supplied, each row also records the earliest era at which the
    configuration becomes available (the maximum era of those technologies,
    ``0`` when none). Nominal values are evaluated at the
    goods table's base prices; the ratio columns follow plain division
    semantics (``x / 0`` is ``inf`` and ``0 / 0`` is ``NaN``).

    Args:
        df_buildings: Buildings table (``BuildingsParser.to_dataframe()`` or
            ``tables/buildings.csv``) with ``key``, ``building_group``,
            ``urbanization``, ``infrastructure_usage_per_level``,
            ``required_construction_points``, ``production_method_groups``,
            and ``unlocking_technologies`` columns. Optional
            ``economy_of_scale`` and ``is_subsistence`` columns determine
            economy-of-scale eligibility; missing columns default to false.
        df_goods: Goods table (`goods` or
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
        df_tech: Optional technology table (`technology` or
            ``tables/technology.csv``) with ``key`` and ``era`` columns. When
            omitted, ``era`` and ``unlocking_tech_localization`` are not
            produced.
        df_pop_types: Optional pop-types table
            (`PopTypesParser.to_dataframe()` or ``tables/pop_types.csv``) with
            ``key``, ``wage_weight``, and ``paid_private_wage`` columns. Missing
            private-wage flags are treated as false. When the table is omitted,
            the wage-normalized employment columns are not produced.

    Returns:
        A ``DataFrame`` with one row per building configuration.  The
        ``"production_method"`` column holds the chosen production methods
        concatenated with ``+``.  The remaining columns are ``"building"``,
        ``"building_group"``, ``"parent_group"``, ``"land_usage"``,
        ``"is_subsistence"``, ``"discoverable_resource"``,
        ``"depletable_resource"``, ``"economy_of_scale"``, ``"urbanization"``,
        ``"infrastructure_usage_per_level"`` (net of the configuration's
        ``state_infrastructure_add`` generation), optional ``"era"``,
        ``"unlocking_tech"``, ``"employment"``, optional
        ``"wage_normalized_employment"``, ``"construction_cost"``,
        ``"value_goods_inputs_nominal"``, ``"value_goods_outputs_nominal"``,
        ``"profit_nominal"``, ``"profit_margin_nominal"``,
        ``"profit_per_capita_nominal"``,
        optional ``"profit_per_wage_normalized_employment_nominal"``, and
        ``"profit_per_construction_cost_nominal"``, followed by one
        ``goods_<good>`` column per good and one ``employment_<profession>``
        column per profession.

    Raises:
        ValueError: If a supplied technology table is missing an unlocking
            technology, or if a supplied pop-types table cannot uniquely
            provide a valid private-wage weight for each employment
            profession.
    """
    goods_cols = [f"goods_{key}" for key in df_goods["key"]]
    profession_cols = [col for col in df_pm.columns if col.startswith("employment_")]
    sum_cols = ["employment", *profession_cols, "state_infrastructure_add", *goods_cols]

    wage_weights: np.ndarray | None = None
    if df_pop_types is not None:
        required_pop_columns = {"key", "wage_weight", "paid_private_wage"}
        missing_pop_columns = required_pop_columns - set(df_pop_types.columns)
        if missing_pop_columns:
            raise ValueError(
                "Pop-types table missing required columns: "
                f"{sorted(missing_pop_columns)}"
            )

        duplicate_pop_keys = df_pop_types.loc[
            df_pop_types["key"].duplicated(keep=False), "key"
        ]
        if not duplicate_pop_keys.empty:
            raise ValueError(
                "Duplicate pop-type keys: "
                f"{sorted(str(key) for key in duplicate_pop_keys.unique())}"
            )

        profession_keys = [
            column.removeprefix("employment_") for column in profession_cols
        ]
        pop_types_by_key = df_pop_types.set_index("key")
        missing_professions = sorted(set(profession_keys) - set(pop_types_by_key.index))
        if missing_professions:
            raise ValueError(
                f"Pop-types table missing employment professions: {missing_professions}"
            )

        profession_pop_types = pop_types_by_key.reindex(profession_keys)
        private_wage_flags = profession_pop_types["paid_private_wage"].fillna(False)
        invalid_private_wage_flags = ~private_wage_flags.map(
            lambda value: isinstance(value, (bool, np.bool_))
        )
        if invalid_private_wage_flags.any():
            invalid_professions = [
                profession
                for profession, invalid in zip(
                    profession_keys, invalid_private_wage_flags
                )
                if invalid
            ]
            raise ValueError(
                "Pop-types table has non-boolean paid_private_wage values for: "
                f"{invalid_professions}"
            )

        private_wage_mask = private_wage_flags.to_numpy(dtype=bool)
        numeric_wage_weights = pd.to_numeric(
            profession_pop_types["wage_weight"], errors="coerce"
        ).to_numpy(dtype=np.float64)
        invalid_wage_weight_mask = private_wage_mask & (
            ~np.isfinite(numeric_wage_weights) | (numeric_wage_weights < 0)
        )
        if invalid_wage_weight_mask.any():
            invalid_professions = [
                profession
                for profession, invalid in zip(
                    profession_keys, invalid_wage_weight_mask
                )
                if invalid
            ]
            raise ValueError(
                "Pop-types table has invalid private wage weights for: "
                f"{invalid_professions}"
            )
        wage_weights = np.where(private_wage_mask, numeric_wage_weights, 0.0)

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

    era_by_tech: dict[str, int] = {}
    if df_tech is not None:
        era_by_tech = {
            key: int(era) for key, era in zip(df_tech["key"], df_tech["era"])
        }

    def localization_map(frame: pd.DataFrame, key: str, value: str) -> dict[str, str]:
        if key not in frame or value not in frame:
            return {}
        return {
            str(item_key): item_value
            for item_key, item_value in zip(frame[key], frame[value])
            if isinstance(item_value, str)
        }

    building_localizations = localization_map(df_buildings, "key", "key_localization")
    has_building_localization = "key_localization" in df_buildings.columns
    building_group_localizations = localization_map(
        df_buildings, "building_group", "building_group_localization"
    )
    has_building_group_localization = (
        "building_group_localization" in df_buildings.columns
    )
    pm_localizations = localization_map(
        df_pm, "production_method", "production_method_localization"
    )
    has_pm_localization = "production_method_localization" in df_pm.columns
    tech_localizations = (
        localization_map(df_tech, "key", "key_localization")
        if df_tech is not None
        else {}
    )
    has_tech_localization = (
        df_tech is not None and "key_localization" in df_tech.columns
    )

    def localize_compound(value: str, values: dict[str, str]) -> object:
        keys = [key for key in value.split("+") if key]
        if not keys:
            return pd.NA
        localized = [values.get(key) for key in keys]
        if any(item is None for item in localized):
            return pd.NA
        return "+".join(item for item in localized if item is not None)

    pm_keys = df_pm["production_method"].tolist()
    pm_techs = [_tech_keys(value) for value in df_pm["unlocking_technologies"]]
    pm_eras = (
        [_era_of_techs(techs, era_by_tech) for techs in pm_techs]
        if df_tech is not None
        else []
    )

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
    economy_of_scale = (
        df_buildings["economy_of_scale"].fillna(False).eq(True)
        if "economy_of_scale" in df_buildings.columns
        else pd.Series(False, index=df_buildings.index)
    )
    is_subsistence = (
        df_buildings["is_subsistence"].fillna(False).eq(True)
        if "is_subsistence" in df_buildings.columns
        else pd.Series(False, index=df_buildings.index)
    )
    economy_of_scale_eligible = economy_of_scale & ~is_subsistence
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
        has_economy_of_scale,
    ) in zip(
        *[df_buildings[column] for column in building_columns],
        economy_of_scale_eligible,
    ):
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
        building_era = (
            _era_of_techs(building_techs, era_by_tech) if df_tech is not None else 0
        )
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
                if df_tech is not None:
                    era = max(era, pm_eras[position])
                techs.extend(pm_techs[position])
            combo_rows.append(
                {
                    "building": building,
                    "production_method": "+".join(
                        pm_keys[position] for position in positions
                    ),
                    "building_group": building_group,
                    "economy_of_scale": bool(has_economy_of_scale),
                    "urbanization": urbanization,
                    "infrastructure_usage_per_level": infrastructure,
                    "unlocking_tech": "+".join(dict.fromkeys(techs)),
                    "construction_cost": int(construction_cost),
                }
            )
            if df_tech is not None:
                combo_rows[-1]["era"] = era
            if has_building_localization:
                combo_rows[-1]["building_localization"] = building_localizations.get(
                    str(building), pd.NA
                )
            if has_pm_localization:
                pm_value = "+".join(pm_keys[position] for position in positions)
                combo_rows[-1]["production_method_localization"] = localize_compound(
                    pm_value, pm_localizations
                )
            if has_building_group_localization:
                combo_rows[-1]["building_group_localization"] = (
                    building_group_localizations.get(str(building_group), pd.NA)
                )
            if has_tech_localization:
                combo_rows[-1]["unlocking_tech_localization"] = localize_compound(
                    "+".join(dict.fromkeys(techs)), tech_localizations
                )
            membership.extend((combo_id, position) for position in positions)

    building_metadata_defaults = {
        "parent_group": pd.NA,
        "land_usage": pd.NA,
        "is_subsistence": False,
        "discoverable_resource": False,
        "depletable_resource": False,
    }
    column_order = [
        "building",
        *(["building_localization"] if has_building_localization else []),
        "production_method",
        *(["production_method_localization"] if has_pm_localization else []),
        "building_group",
        *(["building_group_localization"] if has_building_group_localization else []),
        *building_metadata_defaults,
        "economy_of_scale",
        "urbanization",
        "infrastructure_usage_per_level",
        *(["era"] if df_tech is not None else []),
        "unlocking_tech",
        *(["unlocking_tech_localization"] if has_tech_localization else []),
        "employment",
        *(["wage_normalized_employment"] if wage_weights is not None else []),
        "construction_cost",
        "value_goods_inputs_nominal",
        "value_goods_outputs_nominal",
        "profit_nominal",
        "profit_margin_nominal",
        "profit_per_capita_nominal",
        *(
            ["profit_per_wage_normalized_employment_nominal"]
            if wage_weights is not None
            else []
        ),
        "profit_per_construction_cost_nominal",
        *goods_cols,
        *profession_cols,
    ]
    if not combo_rows:
        empty = pd.DataFrame(columns=column_order)
        for column in column_order:
            if column.endswith("_localization"):
                empty[column] = empty[column].astype("string")
        return empty

    member_positions = [position for _, position in membership]
    combo_ids = [combo_id for combo_id, _ in membership]
    members = df_pm.iloc[member_positions]
    sums = (
        members.groupby(np.asarray(combo_ids), sort=True)[sum_cols]
        .sum()
        .reset_index(drop=True)
    )

    result = pd.concat([pd.DataFrame(combo_rows), sums], axis=1)

    for column, default in building_metadata_defaults.items():
        if column in df_buildings.columns:
            values: dict[str, object] = {
                str(key): value
                for key, value in zip(df_buildings["key"], df_buildings[column])
            }
            result[column] = result["building"].map(
                lambda building, values=values, default=default: values.get(
                    str(building), default
                )
            )
            if isinstance(default, bool):
                result[column] = result[column].fillna(default).eq(True)
        else:
            result[column] = default

    result["infrastructure_usage_per_level"] = (
        result["infrastructure_usage_per_level"] - result["state_infrastructure_add"]
    )
    if wage_weights is not None:
        result["wage_normalized_employment"] = (
            result[profession_cols].to_numpy(dtype=np.float64) @ wage_weights
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
    if wage_weights is not None:
        result["profit_per_wage_normalized_employment_nominal"] = (
            result["profit_nominal"] / result["wage_normalized_employment"]
        )
    result["profit_per_construction_cost_nominal"] = (
        result["profit_nominal"] / result["construction_cost"]
    )

    result = result.reindex(columns=column_order)
    for column in column_order:
        if column.endswith("_localization"):
            result[column] = result[column].astype("string")
    return result
