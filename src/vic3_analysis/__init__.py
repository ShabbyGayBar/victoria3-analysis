"""
vic3_analysis package.

Provides utilities and parsers for analysing Victoria 3 game data, including
buildings, goods, production methods, technologies, and economic optimisation.
"""

from vic3_analysis.utils import get_vic3_directory, parse_merge

from vic3_analysis.parse.buy_packages import buy_packages
from vic3_analysis.parse.buildings import BuildingsParser
from vic3_analysis.parse.goods import goods
from vic3_analysis.parse.pop_needs import PopNeedsParser
from vic3_analysis.parse.pop_types import PopTypesParser
from vic3_analysis.parse.production_method_groups import production_method_groups
from vic3_analysis.parse.production_methods import ProductionMethodParser
from vic3_analysis.parse.state_regions import StateRegionsParser
from vic3_analysis.parse.technology import technology

from vic3_analysis.analysis.production import production_table
from vic3_analysis.analysis.economy import Economy
from vic3_analysis.analysis.supply_chain import (
    Scenario,
    SupplyChainNode,
    ProducerNode,
    upstream_tree,
    build_optimizer,
    optimize_chain,
    value_added_breakdown,
    bottleneck,
    compare_scenarios,
)

from vic3_analysis.optimize.nominal import NominalOptimizer

__all__ = [
    "get_vic3_directory",
    "parse_merge",
    "buy_packages",
    "BuildingsParser",
    "goods",
    "PopNeedsParser",
    "PopTypesParser",
    "production_method_groups",
    "ProductionMethodParser",
    "StateRegionsParser",
    "technology",
    "production_table",
    "Economy",
    "Scenario",
    "SupplyChainNode",
    "ProducerNode",
    "upstream_tree",
    "build_optimizer",
    "optimize_chain",
    "value_added_breakdown",
    "bottleneck",
    "compare_scenarios",
    "NominalOptimizer",
]
