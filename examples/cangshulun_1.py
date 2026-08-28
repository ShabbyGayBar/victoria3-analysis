import numpy as np

from vic3_analysis import Economy, NominalOptimizer


def test_cangshulun1():
    economy = Economy()
    optimizer = NominalOptimizer(economy)

    # 石油只用于开采矿物和制造汽车，即禁止其他消耗石油的生产方式
    banned_pms = [
        "pm_vacuum_canning",
        "pm_vacuum_canning_principle_3",
        "pm_assembly_lines_building_furniture_manufactory",
        "pm_houseware_plastics",
        "pm_automatic_bottle_blowers",
        "pm_assembly_lines_building_tooling_workshop",
        "pm_nitrogen_fixation",
        "pm_diesel_engines",
        "pm_assembly_lines_building_motor_industry",
        # "pm_assembly_lines_building_automotive_industry",
        "pm_bolt_action_rifles",
        "pm_assembly_lines_building_arms_industry",
        "pm_recoiled_barrels",
        "pm_assembly_lines_building_arms_industry",
        "pm_assembly_lines_building_munition_plant",
        "pm_compression_ignition_tractors",
        "pm_oil-fired_plant",
        "pm_chainsaws",
        "pm_modern_port",
        "pm_diesel_trains",
        "pm_diesel_trains_principle_transport_3",
    ]

    # 自动化全开，即最小化人数
    optimizer.objective_vector = optimizer.employment_vector()
    # 禁止进口
    optimizer.constraint_limit_import()
    # 以汽车为终端商品
    optimizer.constraint_produce("automobiles", 10e6 / 5200.0)

    # 全科技，相当于无限制
    # 染料采用合成厂制备，即禁止使用种植园制备染料
    optimizer.constraint_limit_building("building_dye_plantation", 0)
    optimizer.constraint_ban_pm(banned_pms)

    # 求解
    state = optimizer.linprog()
    annual_gdp = float(np.dot(state.building_levels, optimizer.gdp_vector())) * 52
    employment = float(np.sum(state.pops))
    construction_cost = economy.construction_cost(state)
    gdp_per_capita = annual_gdp / employment if employment else float("inf")

    print(f"Optimal GDP: {annual_gdp}")
    print(f"Optimal Employment: {employment}")
    print(f"Optimal GDP per Capita: {gdp_per_capita}")
    print(f"Optimal Construction Cost: {construction_cost}")
    print("GDP per capita (with throughput bonus):", gdp_per_capita * 2.45)
    print("GDP per construction cost:", annual_gdp / construction_cost)

    print("\nOptimal Building Levels:")
    df = economy.buildings_to_df(state)
    print(df)

    print("\nNet Goods Output:")
    net_goods = state.building_levels @ optimizer.goods_matrix
    goods_idx = optimizer.goods_index()
    for g, v in zip(goods_idx, net_goods):
        if abs(v) > 1e-10:
            print(f"  {g}: {v}")


if __name__ == "__main__":
    test_cangshulun1()
