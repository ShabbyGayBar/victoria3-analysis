import pandas as pd

from vic3_analysis import Economy, Scenario, optimize_chain, upstream_tree
from vic3_analysis.analysis.supply_chain import SupplyChainNode
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")


def _recipe_summary(node: SupplyChainNode) -> None:
    """Print each good once with its producer count and input goods."""
    seen: set[str] = set()

    def walk(n: SupplyChainNode) -> None:
        if n.good in seen:
            return
        seen.add(n.good)
        inputs = sorted({g for producer in n.producers for g in producer.inputs})
        label = "raw" if n.is_raw else f"{len(n.producers)} producer(s)"
        inputs_str = ", ".join(inputs) if inputs else "(raw)"
        print(f"  {n.good} [{label}]; inputs: {inputs_str}")
        for producer in n.producers:
            for child in producer.upstream:
                walk(child)

    walk(node)


def _print_realised(
    node: SupplyChainNode, indent: int = 0, seen: set[str] | None = None
) -> None:
    if seen is None:
        seen = set()
    if node.good in seen:
        return
    seen.add(node.good)
    pad = "  " * indent
    label = "raw" if node.is_raw else f"{len(node.producers)} producer(s)"
    print(f"{pad}{node.good} [{label}]")
    for producer in node.producers:
        outputs = ", ".join(f"{g}={v:+.4g}" for g, v in producer.outputs.items())
        print(
            f"{pad}  {producer.building} | {producer.production_method} "
            f"| lvl={producer.level:.4g} -> {outputs}"
        )
        for child in producer.upstream:
            _print_realised(child, indent + 2, seen)


def run_supply_chain_trace():
    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )
    print("=== Recipe trace: automobiles supply-chain map (all producers) ===")
    recipe = upstream_tree(economy, "automobiles")
    _recipe_summary(recipe)

    print("\n=== Realised trace (1 automobile/wk, autarky, max automation) ===")
    state = optimize_chain(
        economy,
        Scenario(
            terminal_good="automobiles",
            target_amount=1.0,
            objective="automation",
        ),
    )
    realised = upstream_tree(economy, "automobiles", state)
    _print_realised(realised)


if __name__ == "__main__":
    run_supply_chain_trace()
