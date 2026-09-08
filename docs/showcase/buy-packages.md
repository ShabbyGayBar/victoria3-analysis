---
title: Buy packages
description: Explore wealth-level political strength and population-need demand in Victoria 3.
---

# Buy packages

Buy packages describe political strength and the amount assigned to each
population-need category at every wealth level. The script writes one table and
one SVG chart for every non-wealth column.

[:fontawesome-brands-github: View `examples/buy_packages.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/buy_packages.py)

```bash
uv run python -m examples.buy_packages
```

## Table preview

Important columns include `wealth`, `political_strength`, `total_popneeds`, and
the individual `popneed_*` categories.

<!-- table-preview: tables/buy_packages.csv | columns=wealth,political_strength,total_popneeds,popneed_basic_food,popneed_services,popneed_luxury_items | rows=5 -->

[:material-download: Download `tables/buy_packages.csv`](../tables/buy_packages.csv)

## Figure gallery

Select a figure to open or download the full SVG.

<div class="figure-gallery">
<figure class="figure-card"><a href="../../figures/buy_packages/political_strength.svg"><img src="../../figures/buy_packages/political_strength.svg" alt="Political strength by wealth"></a><figcaption><code>figures/buy_packages/political_strength.svg</code><br>Political strength</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/total_popneeds.svg"><img src="../../figures/buy_packages/total_popneeds.svg" alt="Total population needs by wealth"></a><figcaption><code>figures/buy_packages/total_popneeds.svg</code><br>Total population needs</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_basic_food.svg"><img src="../../figures/buy_packages/popneed_basic_food.svg" alt="Basic food need by wealth"></a><figcaption><code>figures/buy_packages/popneed_basic_food.svg</code><br>Basic food</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_communication.svg"><img src="../../figures/buy_packages/popneed_communication.svg" alt="Communication need by wealth"></a><figcaption><code>figures/buy_packages/popneed_communication.svg</code><br>Communication</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_crude_items.svg"><img src="../../figures/buy_packages/popneed_crude_items.svg" alt="Crude items need by wealth"></a><figcaption><code>figures/buy_packages/popneed_crude_items.svg</code><br>Crude items</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_free_movement.svg"><img src="../../figures/buy_packages/popneed_free_movement.svg" alt="Free movement need by wealth"></a><figcaption><code>figures/buy_packages/popneed_free_movement.svg</code><br>Free movement</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_heating.svg"><img src="../../figures/buy_packages/popneed_heating.svg" alt="Heating need by wealth"></a><figcaption><code>figures/buy_packages/popneed_heating.svg</code><br>Heating</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_household_items.svg"><img src="../../figures/buy_packages/popneed_household_items.svg" alt="Household items need by wealth"></a><figcaption><code>figures/buy_packages/popneed_household_items.svg</code><br>Household items</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_intoxicants.svg"><img src="../../figures/buy_packages/popneed_intoxicants.svg" alt="Intoxicants need by wealth"></a><figcaption><code>figures/buy_packages/popneed_intoxicants.svg</code><br>Intoxicants</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_leisure.svg"><img src="../../figures/buy_packages/popneed_leisure.svg" alt="Leisure need by wealth"></a><figcaption><code>figures/buy_packages/popneed_leisure.svg</code><br>Leisure</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_luxury_drinks.svg"><img src="../../figures/buy_packages/popneed_luxury_drinks.svg" alt="Luxury drinks need by wealth"></a><figcaption><code>figures/buy_packages/popneed_luxury_drinks.svg</code><br>Luxury drinks</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_luxury_food.svg"><img src="../../figures/buy_packages/popneed_luxury_food.svg" alt="Luxury food need by wealth"></a><figcaption><code>figures/buy_packages/popneed_luxury_food.svg</code><br>Luxury food</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_luxury_items.svg"><img src="../../figures/buy_packages/popneed_luxury_items.svg" alt="Luxury items need by wealth"></a><figcaption><code>figures/buy_packages/popneed_luxury_items.svg</code><br>Luxury items</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_services.svg"><img src="../../figures/buy_packages/popneed_services.svg" alt="Services need by wealth"></a><figcaption><code>figures/buy_packages/popneed_services.svg</code><br>Services</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_simple_clothing.svg"><img src="../../figures/buy_packages/popneed_simple_clothing.svg" alt="Simple clothing need by wealth"></a><figcaption><code>figures/buy_packages/popneed_simple_clothing.svg</code><br>Simple clothing</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_standard_clothing.svg"><img src="../../figures/buy_packages/popneed_standard_clothing.svg" alt="Standard clothing need by wealth"></a><figcaption><code>figures/buy_packages/popneed_standard_clothing.svg</code><br>Standard clothing</figcaption></figure>
<figure class="figure-card"><a href="../../figures/buy_packages/popneed_stimulants.svg"><img src="../../figures/buy_packages/popneed_stimulants.svg" alt="Stimulants need by wealth"></a><figcaption><code>figures/buy_packages/popneed_stimulants.svg</code><br>Stimulants</figcaption></figure>
</div>
