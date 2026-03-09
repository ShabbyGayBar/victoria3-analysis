"""
vic3_analysis package.

Provides utilities and parsers for analysing Victoria 3 game data, including
buildings, goods, production methods, technologies, and economic optimisation.
"""

from vic3_analysis.utils import get_vic3_directory, parse_merge

from vic3_analysis.parse.buy_packages import buy_packages
from vic3_analysis.parse.buildings import BuildingsParser
from vic3_analysis.parse.goods import goods
from vic3_analysis.parse.production_method_groups import production_method_groups
from vic3_analysis.parse.production_methods import production_method
from vic3_analysis.parse.technology import technology

from vic3_analysis.analysis.production import production_table, ProductionAnalyzer
