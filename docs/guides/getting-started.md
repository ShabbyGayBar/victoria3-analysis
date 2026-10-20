---
title: Getting started
description: Set up the package and choose your next analysis workflow.
---

# Getting started

Set up the package, then choose a guide for the analysis you want to run.

## Prepare the checkout

Clone the repository and install its locked development environment:

```bash
git clone --recurse-submodules https://github.com/ShabbyGayBar/victoria3-analysis.git
cd victoria3-analysis
uv sync
```

For an existing checkout, initialize the pinned artifact submodule with
`git submodule update --init --recursive`. The examples require this artifact
checkout. Generate parsed datasets first, then the production table, then study results; see the
[parsing guide](parsing.md#generate-the-tables) for commands and output paths.

## Continue from here

<div class="grid cards" markdown>

- [Parse your installed game](parsing.md) to refresh the source tables.
- [Model economies](economy.md) and evaluate building levels directly.
- [Optimize production](optimization.md) with objectives and constraints.
- [Trace supply chains](supply-chain.md) and compare scenarios.
- [Browse every generated result](../showcase/index.md) and its runnable script.

</div>
