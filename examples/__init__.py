from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
TABLES_DIR = THIS_DIR / ".." / "tables"
FIGURES_DIR = THIS_DIR / ".." / "figures"

DEFAULT_BANNED_BGS = (
    "bg_gold_fields",
    "bg_army",
    "bg_conscription",
    "bg_naval_fortification",
    "bg_naval_administration",
    "bg_naval_logistics_center",
    "bg_army_logistics_center",
    "bg_bureaucracy",
    "bg_technology",
    "bg_skyscraper",
    "bg_monuments",
    "bg_monuments_hidden",
    "bg_canals",
    "bg_trade",
    "bg_manor_houses",
    "bg_financial_districts",
    "bg_subsistence_agriculture",
    "bg_subsistence_ranching",
    "bg_construction",
    "bg_company_headquarter",
    "bg_company_regional_headquarter",
)

CANGSHULUN_BANNED_PMS = (
    # 石油只用于开采矿物和制造汽车，即禁止其他消耗石油的生产方式
    "pm_diesel_engines",
    "pm_oil-fired_plant",
    "pm_houseware_plastics",
    "pm_nitrogen_fixation",
    "pm_assembly_lines_building_tooling_workshop",
    # "pm_mass_automobile_production",
    "pm_bolt_action_rifles",
    "pm_assembly_lines_building_arms_industry",
    "pm_recoiled_barrels",
    "pm_assembly_lines_building_arms_industry",
    "pm_assembly_lines_building_munition_plant",
    "pm_modern_port",
    "pm_diesel_trains_principle_transport_3",
    "pm_diesel_trains",
    "pm_vacuum_canning",
    "pm_vacuum_canning_principle_3",
    "pm_assembly_lines_building_furniture_manufactory",
    "pm_automatic_bottle_blowers",
    "pm_assembly_lines_building_motor_industry",
    # "pm_automobile_production",
    # "pm_assembly_lines_building_automotive_industry",
    # "pm_diesel_pump_building_coal_mine",
    # "pm_diesel_pump_building_iron_mine",
    # "pm_diesel_pump_building_lead_mine",
    # "pm_diesel_pump_building_sulfur_mine",
    # "pm_diesel_pump_building_gold_mine",
    "pm_chainsaws",
    "pm_compression_ignition_tractors",
)
CANGSHULUN_BUILDING_LIMITS = (
    # 染料采用合成厂制备，即禁止使用种植园制备染料
    ("building_dye_plantation", 0.0),
)
