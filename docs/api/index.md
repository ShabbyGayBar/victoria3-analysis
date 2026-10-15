---
title: API reference
description: Public Python API for Victoria 3 parsing, economy modeling, optimization, and supply-chain analysis.
---

# API reference

The reference is generated from type annotations and docstrings in
`src/vic3_analysis`. All package-level exports are documented exactly once and
grouped by workflow.

The [data dictionary](../data-dictionary/index.md) is the column reference for
the tables returned by these APIs.

<div class="grid cards" markdown>

- [Parsing and utilities](parsing.md) — locate game data and construct tables.
- [Economy and production](economy.md) — matrices, states, prices, and reports.
- [Optimization](optimization.md) — scenario definitions and the nominal solver.
- [Supply chains](supply-chain.md) — graphs, attribution, bottlenecks, and comparison.

</div>

If you are learning the package, begin with [Getting started](../guides/getting-started.md) or
the task-focused [guides](../guides/index.md).
