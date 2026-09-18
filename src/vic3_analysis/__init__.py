"""
vic3_analysis package.

Provides utilities and parsers for analysing Victoria 3 game data, including
buildings, goods, production methods, technologies, and economic optimisation.
"""

from vic3_analysis.analysis.economy import Economy
from vic3_analysis.analysis.production import production_table
from vic3_analysis.analysis.supply_chain.analyzer import SupplyChainAnalyzer
from vic3_analysis.analysis.supply_chain.result import (
    SupplyChainResult,
    SupplyChainSweepResult,
)
from vic3_analysis.analysis.supply_chain.sweep import sweep_supply_chains
from vic3_analysis.optimize.base import BaseOptimizer, LinearProblem, MarketProblem
from vic3_analysis.optimize.market import MarketOptimizer
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.scenario import Scenario
from vic3_analysis.parse.building_groups import BuildingGroupParser
from vic3_analysis.parse.buildings import BuildingsParser
from vic3_analysis.parse.buy_packages import buy_packages
from vic3_analysis.parse.goods import goods
from vic3_analysis.parse.localization import localization
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
from vic3_analysis.utils import get_vic3_directory, parse_merge

__all__ = [
    "BaseOptimizer",
    "BuildingGroupParser",
    "BuildingsParser",
    "Economy",
    "LinearProblem",
    "MarketOptimizer",
    "MarketProblem",
    "NominalOptimizer",
    "PopNeedsParser",
    "PopTypesParser",
    "ProductionMethodParser",
    "Scenario",
    "StateRegionsParser",
    "SupplyChainAnalyzer",
    "SupplyChainResult",
    "SupplyChainSweepResult",
    "buy_packages",
    "get_vic3_directory",
    "goods",
    "localization",
    "parse_merge",
    "production_method_groups",
    "production_table",
    "state_region_arable_land_limit",
    "state_region_resource_limits",
    "sweep_supply_chains",
    "technology",
]
