---
title: Economy dependencies
description: Signal-flow graphs for economy calculations, storage ownership, and wealth iteration.
hide:
  - toc
---

# Economy dependencies

These graphs describe the current economy model. An arrow means the source
is needed to calculate the target; it does not imply that every solve mode
runs that calculation. Dashed arrows carry wealth into the next iteration.
Repeated node names refer to the same value across graphs.
Wide diagrams scroll horizontally to preserve readable labels.

For usage, see the [economy guide](../guides/economy.md). The
[API reference](../api/economy.md) describes the public interfaces, and the
[economy data dictionary](../data-dictionary/economy.md) defines report units
and accounting boundaries.

<div class="economy-dependencies" markdown="1">

## Storage legend

<ul class="dependency-legend">
  <li><span class="dependency-owner owner-economy">E</span> <code>Economy</code>: game tables and model coefficients.</li>
  <li><span class="dependency-owner owner-context">C</span> <code>EconomyContext</code>: fixed inputs shared by snapshots.</li>
  <li><span class="dependency-owner owner-market">M</span> <code>MarketState</code>: prices and building finances.</li>
  <li><span class="dependency-owner owner-pop">P</span> <code>PopState</code>: household wealth, demand, and finances.</li>
  <li><span class="dependency-owner owner-state">S</span> <code>EconomyState</code>: the composed snapshot and combined reports.</li>
  <li><span class="dependency-owner owner-variable">V</span> A separate argument, returned value, constant, or solver working variable.</li>
</ul>

An asterisk (`*`) marks a cached property. Methods ending in `()` calculate
their return values on demand without caching them. Textual owner prefixes
remain meaningful without color.

`EconomyState` holds `context`, `market`, and `households` references. Its flat
properties, such as `state.building_goods_flow` and `state.pop_income`, forward
to the component owners shown here; they do not duplicate the arrays.

## Production preparation

Building levels, production coefficients, and effective throughput determine
realized weekly goods flows. Employment scales with building levels, while
throughput changes goods inputs and outputs without scaling worker counts.
Effective throughput adds the economy-of-scale bonus to the supplied multiplier.

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
    nodeSpacing: 20
    rankSpacing: 35
  themeCSS: |
    .node.model rect { fill: var(--vic3-owner-economy) !important; }
    .node.context rect { fill: var(--vic3-owner-context) !important; }
    .node.variable rect { fill: var(--vic3-owner-variable) !important; }
    .node rect { stroke: var(--vic3-owner-border) !important; }
    .nodeLabel { color: var(--vic3-owner-text) !important; }
    .flowchart-link { stroke: var(--vic3-owner-edge) !important; }
    marker path { fill: var(--vic3-owner-edge) !important; stroke: var(--vic3-owner-edge) !important; }
    .edgeLabel, .edgeLabel p { color: var(--vic3-owner-text) !important; background: var(--md-default-bg-color) !important; }
---
flowchart TD
    DP["[E] df_production"]:::model
    PC["[E] Unscaled goods matrices *"]:::model
    EM["[E] employment_matrix *"]:::model
    DP --> PC
    DP --> EM

    L["[C] building_levels"]:::context
    CAP["[V] economy_of_scale_level_cap"]:::variable
    TM["[V] throughput_multipliers"]:::variable

    L --> EOS["[V] Economy-of-scale bonuses"]:::variable
    CAP --> EOS
    DP --> EOS
    EOS --> T["[V] Effective throughput"]:::variable
    TM --> T

    L --> F["[C] building_goods_flow"]:::context
    PC --> F
    T --> F

    F --> GI["[C] building_goods_input *"]:::context
    F --> GO["[C] building_goods_output *"]:::context

    GO --> SELL["[C] sell_orders *"]:::context
    TF["[C] goods_trade_flow"]:::context --> IM["[C] imports *"]:::context
    IM --> SELL

    GI --> NP["[C] non_pop_buy_orders *"]:::context
    TF --> EX["[C] exports *"]:::context
    EX --> NP

    L --> N["[C] pops"]:::context
    EM --> N

```

Flows retain the production table's signed-net convention within each
configuration. Splitting signs before aggregation preserves opposing orders
between different configurations. No separate gross-flow parsing is implied.

## Consumption and market prices

`Economy.df_buy_packages` contains raw need-category budgets at base prices.
Prepared `EconomyContext.buy_packages` contains goods quantities by wealth
tier; `buy_package_wealth` labels its rows. These are different representations.

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
    nodeSpacing: 20
    rankSpacing: 35
  themeCSS: |
    .node.model rect { fill: var(--vic3-owner-economy) !important; }
    .node.context rect { fill: var(--vic3-owner-context) !important; }
    .node.market rect { fill: var(--vic3-owner-market) !important; }
    .node.household rect { fill: var(--vic3-owner-pop) !important; }
    .node.snapshot rect { fill: var(--vic3-owner-state) !important; }
    .node.variable rect { fill: var(--vic3-owner-variable) !important; }
    .node rect { stroke: var(--vic3-owner-border) !important; }
    .nodeLabel { color: var(--vic3-owner-text) !important; }
    .flowchart-link { stroke: var(--vic3-owner-edge) !important; }
    marker path { fill: var(--vic3-owner-edge) !important; stroke: var(--vic3-owner-edge) !important; }
    .edgeLabel, .edgeLabel p { color: var(--vic3-owner-text) !important; background: var(--md-default-bg-color) !important; }
---
flowchart TD
    N["[C] pops"]:::context --> SC["[C] consumption_scales"]:::context
    R["[C] workforce_ratio"]:::context --> D["[C] dependents_per_worker *"]:::context
    D --> SC
    CM["[E] _pop_consumption_multipliers *"]:::model --> SC

    SELL["[C] sell_orders *"]:::context --> ES["[V] Effective substitution supply"]:::variable
    NP["[C] non_pop_buy_orders *"]:::context --> ES

    ES --> SH["[V] Substitution shares"]:::variable
    PN["[E] df_pop_needs"]:::model --> SH

    SH --> Q["[C] buy_packages<br/>+ buy_package_wealth"]:::context
    RAW["[E] df_buy_packages<br/>Raw category budgets"]:::model --> Q
    BASE["[E] base_prices *"]:::model --> Q

    Q --> NEEDS["[P] pop_needs"]:::household
    SC --> NEEDS
    W["[P] pop_wealth"]:::household --> NEEDS

    NEEDS --> BUY["[S] buy_orders *"]:::snapshot
    NP --> BUY

    BUY --> PRICE["[M] market_prices"]:::market
    SELL --> PRICE
    BASE --> PRICE

```

Prepared baskets and scales are optional context fields. `prepare_context()`
computes only missing fields; supplied fields are authoritative. Baskets stay
fixed while production, trade, and substitution assumptions are fixed. Scales
stay fixed while worker counts, workforce ratio, and profession multipliers
are fixed. Changing wealth selects different basket rows; changing prices
changes their monetary cost rather than their quantities.

`calculate_buy_packages()` returns an independent DataFrame for inspection.
`calculate_pop_consumption_scales()`, `calculate_pop_needs()`, and
`calculate_pop_expenses()` return arrays without updating a snapshot.
Preparation and wealth evaluation attach the appropriate results to their
owners. The evaluator calculates total buy orders as a working array; the
composed snapshot exposes the same quantity through cached `buy_orders`.

## Household finances and iteration

Cooperative income distributes each configuration's positive value added
according to worker counts and profession wage weights. Dependent earnings
are added separately. Expenses value the selected baskets at the same market
prices. Basket costs, income coefficients, and transitions are solver working
values, rather than additional public state fields.

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
    nodeSpacing: 20
    rankSpacing: 35
  themeCSS: |
    .node.model rect { fill: var(--vic3-owner-economy) !important; }
    .node.context rect { fill: var(--vic3-owner-context) !important; }
    .node.market rect { fill: var(--vic3-owner-market) !important; }
    .node.household rect { fill: var(--vic3-owner-pop) !important; }
    .node.variable rect { fill: var(--vic3-owner-variable) !important; }
    .node rect { stroke: var(--vic3-owner-border) !important; }
    .nodeLabel { color: var(--vic3-owner-text) !important; }
    .flowchart-link { stroke: var(--vic3-owner-edge) !important; }
    marker path { fill: var(--vic3-owner-edge) !important; stroke: var(--vic3-owner-edge) !important; }
    .edgeLabel, .edgeLabel p { color: var(--vic3-owner-text) !important; background: var(--md-default-bg-color) !important; }
---
flowchart TD
    F["[C] building_goods_flow"]:::context --> SUR["[M] building_surplus *"]:::market
    PRICE["[M] market_prices"]:::market --> SUR
    SUR --> DEF["[M] building_deficit *"]:::market

    N["[C] pops"]:::context --> SH["[V] Cooperative allocation shares"]:::variable
    WW["[E] pop_wage_weights *"]:::model --> SH

    SUR --> CI["[V] Cooperative income<br/>Positive surplus only"]:::variable
    SH --> CI

    N --> DI["[V] Dependent income"]:::variable
    D["[C] dependents_per_worker *"]:::context --> DI
    DW["[E] df_pop_types.dependent_wage"]:::model --> DI

    CI --> INC["[P] pop_income"]:::household
    DI --> INC

    Q["[C] buy_packages<br/>+ buy_package_wealth"]:::context --> BC["[V] Basket costs by wealth"]:::variable
    PRICE --> BC

    BC --> EXP["[P] pop_expenses"]:::household
    W["[P] pop_wealth at t"]:::household --> EXP
    SC["[C] consumption_scales"]:::context --> EXP

    INC --> BAL["[P] pop_balance *"]:::household
    EXP --> BAL

    BC --> COSTS["[V] Current- and next-tier<br/>household costs"]:::variable
    W --> COSTS
    SC --> COSTS

    COSTS --> RULE["[V] Wealth transition"]:::variable
    INC --> RULE
    W --> RULE
    TH["[V] 0.98 / 1.02 constants<br/>+ rtol / atol"]:::variable --> RULE

    RULE --> NW["[P] pop_wealth at t + 1"]:::household
    NW -. "Next evaluation" .-> W

```

`evaluate_wealth(context, pop_wealth)` evaluates one assignment without changing
wealth and returns matching `MarketState` and `PopState` components. `iterate()`
trusts consistent evaluated inputs, applies simultaneous one-tier changes using
the previous prices and income, and evaluates the new assignment. It shares the
fixed context and returns the original components when wealth is unchanged.

The transition decreases wealth below 98% of current-tier cost; otherwise it
increases wealth at or above 102% of next-tier cost, within configured numerical
tolerances. Decreases take precedence, and minimum/maximum tiers bound movement.
`solve(method="equilibrium")` repeats evaluation and transition, detects cycles
and iteration limits, and independently verifies a stationary result. Numerical
convergence does not guarantee affordability at the minimum tier or funded
building losses; `equilibrium_diagnostics` records these flags on `EconomyState`.

`pop_income` and `pop_expenses` are optional `PopState` fields. Nominal and market
solves leave them unevaluated, and `pop_balance` is `None` until both are supplied.
When evaluated, balance is the signed weekly difference between income and
expenses; it is not an accumulated savings stock.

## Derived reports

Fixed population metrics belong to the context, price-valued production metrics
belong to the market, and reports combining wealth with fixed population data
belong to the composed economy snapshot.

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
    nodeSpacing: 20
    rankSpacing: 35
  themeCSS: |
    .node.context rect { fill: var(--vic3-owner-context) !important; }
    .node.market rect { fill: var(--vic3-owner-market) !important; }
    .node.household rect { fill: var(--vic3-owner-pop) !important; }
    .node.snapshot rect { fill: var(--vic3-owner-state) !important; }
    .node rect { stroke: var(--vic3-owner-border) !important; }
    .nodeLabel { color: var(--vic3-owner-text) !important; }
    .flowchart-link { stroke: var(--vic3-owner-edge) !important; }
    marker path { fill: var(--vic3-owner-edge) !important; stroke: var(--vic3-owner-edge) !important; }
    .edgeLabel, .edgeLabel p { color: var(--vic3-owner-text) !important; background: var(--md-default-bg-color) !important; }
---
flowchart TD
    F["[C] building_goods_flow"]:::context --> GDP["[M] gdp_weekly *"]:::market
    PRICE["[M] market_prices"]:::market --> GDP
    GDP --> AGDP["[M] gdp(annual=True)"]:::market

    N["[C] pops"]:::context --> EMP["[C] total_employment *"]:::context
    EMP --> POP["[C] total_population *"]:::context
    R["[C] workforce_ratio"]:::context --> POP

    GDP --> GDPC["[S] gdp_per_capita()"]:::snapshot
    POP --> GDPC

    N --> EP["[C] employment_by_profession *"]:::context
    EP --> PS["[C] profession_shares *"]:::context
    EMP --> PS

    W["[P] pop_wealth"]:::household --> WT["[S] total_wealth_by_profession *"]:::snapshot
    N --> WT
    WT --> AW["[S] average_wealth *"]:::snapshot
    EMP --> AW
    WT --> WP["[S] average_wealth_by_profession *"]:::snapshot
    EP --> WP

    W --> WS["[S] wealth_distribution *"]:::snapshot
    N --> WS
    AW --> WS
    W --> GW["[S] gini_wealth *"]:::snapshot
    N --> GW

    WT --> TW["[S] total_wealth *"]:::snapshot
    R --> TW

```

Wealth statistics describe integer consumption tiers rather than monetary
assets. GDP is production value added; it does not include the exogenous
dependent earnings added to household income. Employment-weighted profession
totals are cached once and shared by the wealth summaries and population report.
The uniform workforce ratio makes per-capita wealth equal to average wealth.

</div>
