"""
vic3_analysis package.

Provides utilities and parsers for analysing Victoria 3 game data, including
buildings, goods, production methods, technologies, and economic optimisation.
"""

from vic3_analysis.utils import get_vic3_directory, parse_merge

from vic3_analysis.parse.buy_packages import buy_packages
from vic3_analysis.parse.building_groups import BuildingGroupParser
from vic3_analysis.parse.buildings import BuildingsParser
from vic3_analysis.parse.goods import goods
from vic3_analysis.parse.pop_needs import PopNeedsParser
from vic3_analysis.parse.pop_types import PopTypesParser
from vic3_analysis.parse.production_method_groups import production_method_groups
from vic3_analysis.parse.production_methods import ProductionMethodParser
from vic3_analysis.parse.state_regions import (
    StateRegionsParser,
    state_region_arable_land_limit,
    state_region_resource_limits,
)
from vic3_analysis.parse.technology import technology

from vic3_analysis.analysis.production import production_table
from vic3_analysis.analysis.economy import Economy
from vic3_analysis.optimize.scenario import Scenario
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.market import MarketOptimizer
from vic3_analysis.analysis.supply_chain import (
    SupplyChainNode,
    ProducerNode,
    upstream_tree,
    optimize_chain,
    value_added_breakdown,
    bottleneck,
    compare_scenarios,
)

__all__ = [
    "get_vic3_directory",
    "parse_merge",
    "buy_packages",
    "BuildingsParser",
    "BuildingGroupParser",
    "goods",
    "PopNeedsParser",
    "PopTypesParser",
    "production_method_groups",
    "ProductionMethodParser",
    "StateRegionsParser",
    "state_region_arable_land_limit",
    "state_region_resource_limits",
    "technology",
    "production_table",
    "Economy",
    "Scenario",
    "NominalOptimizer",
    "MarketOptimizer",
    "SupplyChainNode",
    "ProducerNode",
    "upstream_tree",
    "optimize_chain",
    "value_added_breakdown",
    "bottleneck",
    "compare_scenarios",
]
