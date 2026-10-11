---
title: Supply-chain design references
description: Architectural parallels with Brightway, PyPSA, Calliope, pymrio, and openLCA.
---

# Supply-chain design references

The nominal supply-chain analyzer combines a goods/process graph, constrained
optimization, and economic reports. These projects provide useful references
for different parts of that design. The comparisons below describe
architectural parallels; they do not establish implementation provenance or
imply dependencies on these packages.

For usage, see the [supply-chain guide](guides/supply-chain.md). For exact
formulas and report boundaries, see the
[supply-chain data dictionary](data-dictionary/supply-chain.md).

| Reference | Most relevant design topic | Corresponding part of this package |
| --- | --- | --- |
| [Brightway](#brightway-processes-products-and-cycles) | Separate transformations from products. | Bipartite graphs, process naming, matrix-backed flows. |
| [PyPSA](#pypsa-conversions-optimization-and-duals) | Optimize conversion levels and expose constraint duals. | Compiled problems, adjusted rates, constraints and bottlenecks. |
| [Calliope](#calliope-technologies-and-shared-resources) | Model multiple carriers and shared deployment limits. | PM configurations, coproducts, common land/resource budgets. |
| [pymrio](#pymrio-demand-and-economic-accounting) | Trace economic requirements and production factors. | Value added, employment, explicit accounting scope. |
| [openLCA](#openlca-explicit-coproduct-allocation) | Make coproduct attribution a modeling choice. | Exact process contributions without implicit good-level allocation. |

## Brightway: processes, products, and cycles

Brightway encourages a separate process/product inventory model, while also
supporting combined process/product nodes used in existing datasets. A process
can have multiple functional edges. This supports our choice to model a
complete building/PM configuration as a process, keep goods independent of
their producers, and retain every coproduct output. The guide explains
[why building, method, producer, and recipe name different concepts](guides/supply-chain.md#why-the-graph-uses-processes).
[Brightway inventory model](https://docs.brightway.dev/en/latest/content/overview/inventory.html#processes-products-and-something-in-between).

Our physical directions, good → consuming process and process → output good,
agree with Brightway's newer interface-schema design. Older Brightway exchange
`input`/`output` fields do not consistently encode physical direction and
should not be mapped directly to our graph roles.
[Brightway interface schemas](https://github.com/brightway-lca/bw_interface_schemas#design-decisions),
[exchange conventions](https://docs.brightway.dev/en/latest/content/overview/matrix.html#what-data-enters-the-technosphere-matrix).

Brightway calculates from a technosphere matrix and caches numerical data
separately from stored inventory. We similarly use compiled matrices for
solving and reports, with cached economy coefficients. Matrix orientation
differs: our rows are configurations and columns are goods; Brightway's rows
are products and columns are processes. Our owned result snapshots are a
project-specific reproducibility choice.
[Brightway matrix construction](https://docs.brightway.dev/en/latest/content/overview/matrix.html).

The terminal target is analogous to product demand in a functional unit, but
our quantity is a lower bound on net production. Equal base-price value in a
sweep is an economic normalization; it does not establish equivalent product
functions. Brightway allows a functional unit containing several products;
our analyzer deliberately supports one terminal target per solve.
[Brightway functional unit](https://docs.brightway.dev/en/latest/content/overview/glossary.html#functional-unit).

Brightway Graph Tools describes cyclic supply chains and traversal nodes
created for individual visits. Our retained graph instead has one stable node
per configuration and measures strongly connected components and condensation
depth. Diagram pruning changes presentation without inventing resource leaves.
[Brightway traversal nodes](https://docs.brightway.dev/projects/graphtools/en/latest/content/api/bw_graph_tools/graph_traversal/graph_objects/index.html#bw_graph_tools.graph_traversal.graph_objects.Node).

Brightway's standard inventory calculation solves a matrix system for demand;
our linear program selects production levels under scenario constraints.
Brightway also models biosphere flows and environmental impact
characterization. Our game resource flags and economic metrics do not represent
environmental impact scores.
[Brightway calculation and matrix roles](https://docs.brightway.dev/en/latest/content/overview/matrix.html).

## PyPSA: conversions, optimization, and duals

PyPSA's current `Process` component scales signed input/output rates by one
internal dispatch variable. Its `Link` component also represents conversions
with multiple inputs and outputs. This closely parallels our use of one solved
configuration level to scale all adjusted goods coefficients. PyPSA's rates
scale dispatch; ours specify weekly goods flows per building level, so the
units and capacity interpretation differ.
[PyPSA Process](https://docs.pypsa.org/latest/user-guide/components/processes/),
[PyPSA Link](https://docs.pypsa.org/latest/user-guide/components/links/).

PyPSA exposes separate model creation and solving methods and maps solution
values and constraint duals back to network components. This is a useful
parallel for `NominalOptimizer.compile()`, `solve_problem()`, and named
constraint reporting. We retain raw HiGHS marginals and normalize their signs
for objective improvement. `bottlenecks()` uses binding constraints with useful
marginals; a large input cost share alone does not identify a binding limit.
[PyPSA optimization API](https://docs.pypsa.org/latest/api/networks/optimize/).

The analogy concerns conversion coefficients and optimization diagnostics.
Our nominal analyzer describes a single weekly production system; it does not
implement PyPSA's time-dependent dispatch, storage, or electrical network
equations.

## Calliope: technologies and shared resources

Calliope models technologies with multiple input/output carriers, including
coproduction and alternative carriers. It also supports area use tied to
technology capacity and a shared available-area constraint. These provide a
useful comparison for complete PM configurations with multiple goods and for
technologies competing for a common resource budget.
[Calliope multiple carriers and area constraints](https://calliope.readthedocs.io/en/latest/how_to/constraints/).

In our implementation, each PM combination is a separate process with fixed
adjusted coefficients. A scenario-wide land cap constrains the combined
deployment of all applicable configurations. Per-building limits constrain
the combined levels of that building's configurations. The `allowed` view
records static technology eligibility; shared budgets can still make an
otherwise allowed route infeasible. The `realized` view uses the levels chosen
by the one optimization solve.

Calliope's carrier and area models are analogies for our goods and land
budgets. They do not imply that the analyzer supports carrier switching within
one configuration, geographic energy networks, or storage across timesteps.

## pymrio: demand and economic accounting

pymrio computes industry output from final demand using a Leontief requirement
matrix. Its extensions can track production factors such as value added and
employment, with direct and indirect requirements and distinct production,
consumption, import, and export accounts. This makes it a useful reference for
describing what an economic supply-chain metric measures and which boundary
it uses.
[pymrio mathematical background](https://pymrio.readthedocs.io/en/latest/math.html).

Our reports similarly value goods flows and scale employment coefficients by
solved production levels. However, `system_*` includes every solved
configuration, while `chain_*` sums the full contributions of active terminal
ancestors, including their coproducts. Those graph-defined totals are not
pymrio consumption-based accounts or an allocation of indirect requirements
to final demand. Equal-value sweeps compare separate optimized scenarios.

pymrio uses aggregate sector/region input-output relationships. Our model
keeps individual production configurations and chooses among them through an
LP; it does not calculate a Leontief inverse. A process's whole contribution
can belong to several separately analyzed terminal chains, so adding their
chain totals can double-count it.

## openLCA: explicit coproduct allocation

openLCA exposes physical, causal, and economic allocation, as well as system
expansion, for processes involving multiple products. Physical allocation uses
physical relationships; economic allocation uses cost/revenue relationships;
causal allocation requires modeled assumptions. These are distinct policies
that can change attribution even when the underlying process is unchanged.
[openLCA allocation manual](https://greendelta.github.io/openLCA2-manual/allocation.html).

This illustrates why our API retains exact process-level GDP, employment, and
construction contributions without assigning them to output goods. For a
process producing two goods, its input cost, employment, and value added are
well-defined. How much belongs to each output is an additional modeling
decision. Any future good-level allocation needs a named policy, an explicit
basis, and reconciliation tests.

openLCA allocates LCA inventories and impacts. It does not provide a default
rule for our economic reports. In particular, retaining whole-process
contributions in a terminal graph is not a claim that those contributions
belong exclusively to that terminal good.
