---
title: Buy Packages Analysis
description: Wealth levels, political strength, total consumption, and spending on individual needs.
date: 2026-11-06
game_version: "1.15.0"
---

# Buy Packages Analysis

**English** · [简体中文](buy-packages-zh-CN.md)

!!! info "Verified for Victoria 3 1.13.11 and 1.15"

    Verified on **2026-11-06**. The 1.15 buy-package CSV is identical to the 1.13.11 CSV, including political strength and all 15 need categories. Both versions share this article and its charts from the pinned historical commit.

## Wealth level vs political strength

Levels 1–99 can be roughly divided into three ranges.

- Below level 20, growth is rapid, but the increase per level is not fixed.
- Levels 20–49 show piecewise linear growth, with progressively larger increments per level.
- From level 50 onward, growth is linear: each additional wealth level adds 25 points of political strength.

[![Political strength at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength.svg)

*Political strength at each wealth level*

[![Political strength at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength_log.svg)

*Political strength at each wealth level on a logarithmic scale*

## Wealth level vs total consumption

Growth is roughly exponential. Each additional wealth level multiplies the total consumption budget by about 1.1.

[![Total consumption budget at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds.svg)

*Total consumption budget at each wealth level*

[![Total consumption budget at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds_log.svg)

*Total consumption budget at each wealth level on a logarithmic scale*

## Wealth level vs consumption by need category

### Simple clothing

Demand first rises and then falls at low wealth levels, reaching zero at level 15.

[![Simple clothing demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_simple_clothing.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_simple_clothing.svg)

*Simple clothing demand at each wealth level*

### Basic food

At low wealth levels, demand first rises and then fluctuates around 160. It drops sharply from level 27 and is zero from level 30 onward.

[![Basic food demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_basic_food.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_basic_food.svg)

*Basic food demand at each wealth level*

### Heating

A necessity. Demand increases below level 10 and is fixed at 26 from level 10 onward.

[![Heating demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_heating.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_heating.svg)

*Heating demand at each wealth level*

### Household items

Demand is zero below level 10, then generally increases. It stays at 238 from levels 31–44 before suddenly dropping to zero at level 45.

[![Household items demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_household_items.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_household_items.svg)

*Household items demand at each wealth level*

### Crude items

Demand is zero below level 5, then rises and falls before returning to zero at level 15.

[![Crude items demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_crude_items.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_crude_items.svg)

*Crude items demand at each wealth level*

### Standard clothing

Demand is zero below level 10. It reaches 161 at level 26 and stays constant until suddenly dropping to zero at level 40.

[![Standard clothing demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_standard_clothing.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_standard_clothing.svg)

*Standard clothing demand at each wealth level*

### Services

Demand is zero below level 10, then grows roughly exponentially. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Services demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services.svg)

*Services demand at each wealth level*

[![Services demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services_log.svg)

*Services demand at each wealth level on a logarithmic scale*

### Intoxicants

A necessity. Demand generally increases below level 30, then stays at 216 from level 30 onward.

[![Intoxicants demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_intoxicants.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_intoxicants.svg)

*Intoxicants demand at each wealth level*

### Luxury drinks

Demand is zero below level 15, then grows roughly exponentially. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Luxury drinks demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks.svg)

*Luxury drinks demand at each wealth level*

[![Luxury drinks demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks_log.svg)

*Luxury drinks demand at each wealth level on a logarithmic scale*

### Free movement

Demand is zero below level 10, then grows roughly exponentially. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Free movement demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement.svg)

*Free movement demand at each wealth level*

[![Free movement demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement_log.svg)

*Free movement demand at each wealth level on a logarithmic scale*

### Communication

Demand is zero below level 20, then grows unevenly until around level 40, followed by roughly exponential growth. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Communication demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication.svg)

*Communication demand at each wealth level*

[![Communication demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication_log.svg)

*Communication demand at each wealth level on a logarithmic scale*

### Luxury food

Demand is zero below level 20, then grows roughly exponentially. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Luxury food demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food.svg)

*Luxury food demand at each wealth level*

[![Luxury food demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food_log.svg)

*Luxury food demand at each wealth level on a logarithmic scale*

### Luxury items

Demand is zero below level 15, then grows roughly exponentially. At high wealth levels, each additional level multiplies the budget by about 1.1.

[![Luxury items demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items.svg)

*Luxury items demand at each wealth level*

[![Luxury items demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items_log.svg)

*Luxury items demand at each wealth level on a logarithmic scale*

### Leisure

Demand is zero below level 20, then grows roughly exponentially, with each additional level multiplying the budget by about 1.2 over some intervals. At high wealth levels, growth remains roughly exponential, but the multiplier per level is about 1.1.

[![Leisure demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure.svg)

*Leisure demand at each wealth level*

[![Leisure demand at each wealth level on a logarithmic scale](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure_log.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure_log.svg)

*Leisure demand at each wealth level on a logarithmic scale*

### Stimulants

Demand is zero below level 6, then rises and falls before returning to zero at level 31.

[![Stimulants demand at each wealth level](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_stimulants.svg)](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_stimulants.svg)

*Stimulants demand at each wealth level*

## Terminology

- Need categories are the “consumption groups” discussed in [BV1pG3yzVE67](https://www.bilibili.com/video/BV1pG3yzVE67).
- Consumption, the vertical axis of each chart, is the weekly base-price budget for that need category per 10,000 working adults, rather than actual market spending or goods quantities. Dependents have half the baseline consumption weight of working adults.
- Wealth level, the horizontal axis of each chart, determines a person's total weekly consumption budget. Wealth falls when income cannot cover the current buy package and rises when income can cover a higher-level package. It is closely related to standard of living (SoL), but the two are not identical.

## Appendix: data and reproduction

- GitHub repository: [victoria3-analysis](https://github.com/ShabbyGayBar/victoria3-analysis)
- Full-resolution SVG versions of the charts: [all SVG figures](#all-svg-figures).
- The table shown at 00:26 in [BV1pG3yzVE67](https://www.bilibili.com/video/BV1pG3yzVE67): [buy_packages.csv](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/buy_packages.csv)
- More game data tables: [parsed data](parsed-data.md)
- Source code that generates these tables: [`examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/main/examples/parse.py)

### Table preview

| wealth | political_strength | total_popneeds | popneed_basic_food | popneed_services | popneed_luxury_items |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.03 | 151 | 90 | 0 | 0 |
| 2 | 0.04 | 165 | 94 | 0 | 0 |
| 3 | 0.05 | 181 | 98 | 0 | 0 |
| 4 | 0.1 | 200 | 105 | 0 | 0 |
| 5 | 0.15 | 221 | 106 | 0 | 0 |

[:material-download: Download the complete CSV `datasets/parsed/buy_packages/buy_packages.csv`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/buy_packages.csv)

### All SVG figures

Linear and logarithmic versions of 17 metrics: 34 SVGs in total.

| Metric | Linear scale | Logarithmic scale |
| --- | --- | --- |
| Political strength | [`political_strength.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength.svg) | [`political_strength_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/political_strength_log.svg) |
| Total consumption budget | [`total_popneeds.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds.svg) | [`total_popneeds_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/total_popneeds_log.svg) |
| Simple clothing | [`popneed_simple_clothing.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_simple_clothing.svg) | [`popneed_simple_clothing_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_simple_clothing_log.svg) |
| Basic food | [`popneed_basic_food.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_basic_food.svg) | [`popneed_basic_food_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_basic_food_log.svg) |
| Heating | [`popneed_heating.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_heating.svg) | [`popneed_heating_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_heating_log.svg) |
| Household items | [`popneed_household_items.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_household_items.svg) | [`popneed_household_items_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_household_items_log.svg) |
| Crude items | [`popneed_crude_items.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_crude_items.svg) | [`popneed_crude_items_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_crude_items_log.svg) |
| Standard clothing | [`popneed_standard_clothing.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_standard_clothing.svg) | [`popneed_standard_clothing_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_standard_clothing_log.svg) |
| Services | [`popneed_services.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services.svg) | [`popneed_services_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_services_log.svg) |
| Intoxicants | [`popneed_intoxicants.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_intoxicants.svg) | [`popneed_intoxicants_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_intoxicants_log.svg) |
| Luxury drinks | [`popneed_luxury_drinks.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks.svg) | [`popneed_luxury_drinks_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_drinks_log.svg) |
| Free movement | [`popneed_free_movement.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement.svg) | [`popneed_free_movement_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_free_movement_log.svg) |
| Communication | [`popneed_communication.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication.svg) | [`popneed_communication_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_communication_log.svg) |
| Luxury food | [`popneed_luxury_food.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food.svg) | [`popneed_luxury_food_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_food_log.svg) |
| Luxury items | [`popneed_luxury_items.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items.svg) | [`popneed_luxury_items_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_luxury_items_log.svg) |
| Leisure | [`popneed_leisure.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure.svg) | [`popneed_leisure_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_leisure_log.svg) |
| Stimulants | [`popneed_stimulants.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_stimulants.svg) | [`popneed_stimulants_log.svg`](https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/parsed/buy_packages/figures/popneed_stimulants_log.svg) |

### Reproduction

Run from the project root:

```bash
uv run python -m examples.parse
```

See the [parsing guide](../guides/parsing.md) for setup and game-file detection, and the [buy-package data dictionary](../data-dictionary/parsers.md#buy-packages) for field definitions. The data and findings are verified for 1.13.11 and 1.15; regenerated outputs depend on the installed game version.

### Historical source and current exports

The displayed CSV and all 34 SVGs link directly to artifact [commit `19fdf73d3453da8c152e29223f826536c8e6b33c`](https://github.com/ShabbyGayBar/victoria3-analysis-artifacts/tree/19fdf73d3453da8c152e29223f826536c8e6b33c). The five-row preview above was extracted from the same commit. Parsing the 1.15 game files reproduces the same CSV. Historical files remain in Git history; no copies are stored in the current artifact collections.

Current generated exports: [buy_packages.csv](../artifacts/datasets/parsed/buy_packages/buy_packages.csv). Current SVGs use the filenames listed above under `datasets/parsed/buy_packages/figures`; [browse the current figures](https://github.com/ShabbyGayBar/victoria3-analysis-artifacts/tree/main/datasets/parsed/buy_packages/figures). These exports may change when regenerated for another game version.
