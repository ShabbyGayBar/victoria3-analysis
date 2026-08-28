import numpy as np

from vic3_analysis import BuildingsParser, Economy, NominalOptimizer


def test_cangshulun2():
    economy = Economy()
    optimizer = NominalOptimizer(economy)

    # 读取建筑类型数据
    bg_dict = BuildingsParser().building_groups()
    # 制造业145%吞吐量加成
    for building_key in bg_dict.get("bg_light_industry", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_heavy_industry", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_military_industry", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_private_infrastructure", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_power", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_trade", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    # 农业145%吞吐量加成
    for building_key in bg_dict.get("bg_staple_crops", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_ranching", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_agriculture", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_plantations", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_staple_crops", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    for building_key in bg_dict.get("bg_staple_crops", []):
        optimizer.add_throughput_bonus(building_key, 2.45)
    # 资源产业115%吞吐量加成
    for building_key in bg_dict.get("bg_mining", []):
        optimizer.add_throughput_bonus(building_key, 2.15)
    for building_key in bg_dict.get("bg_logging", []):
        optimizer.add_throughput_bonus(building_key, 2.15)
    for building_key in bg_dict.get("bg_rubber", []):
        optimizer.add_throughput_bonus(building_key, 2.15)
    for building_key in bg_dict.get("bg_fishing", []):
        optimizer.add_throughput_bonus(building_key, 2.15)
    for building_key in bg_dict.get("bg_whaling", []):
        optimizer.add_throughput_bonus(building_key, 2.15)
    for building_key in bg_dict.get("bg_oil_extraction", []):
        optimizer.add_throughput_bonus(building_key, 2.15)

    banned_pms = [
        # 种植园使用标准条件进行生产
        "slave_exploitation_coffee",
        "worker_exploitation_coffee",
        "slave_exploitation_cotton",
        "worker_exploitation_cotton",
        "slave_exploitation_dye",
        "worker_exploitation_dye",
        "slave_exploitation_tea",
        "worker_exploitation_tea",
        "worker_exploitation_tobacco",
        "lectors_tobacco",
        "radio_stations_tobacco",
        "slave_exploitation_sugar",
        "worker_exploitation_sugar",
        "slave_exploitation_banana",
        "worker_exploitation_banana",
        "slave_exploitation_rubber",
        "worker_exploitation_rubber",
        "pm_rayon",  # 丝绸使用种植园生产，即禁止使用合成厂生产丝绸
        "pm_oil-fired_plant",  # 电力使用燃煤发电，即禁止电厂烧石油
        # 玻璃使用最先进方式生产
        "pm_forest_glass",
        "pm_leaded_glass",
        "pm_crystal_glass",
    ]

    # 自动化全开，即最小化人数
    optimizer.objective_vector = optimizer.employment_vector()
    # 禁止进口
    optimizer.constraint_limit_import()
    # 终端商品
    optimizer.constraint_produce("oil", 100)

    # 尾盘全科技，相当于无限制
    # 染料采用合成厂制备，即禁止使用种植园制备染料    optimizer.constraint_limit_building("building_dye_plantation", 0)
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

    print("\nOptimal Building Levels:")
    df = economy.df_buildings(state)
    print(df)

    print("\nNet Goods Output:")
    net_goods = state.building_levels @ optimizer.goods_matrix
    goods_idx = optimizer.goods_index()
    for g, v in zip(goods_idx, net_goods):
        if abs(v) > 1e-10:
            print(f"  {g}: {v}")


if __name__ == "__main__":
    test_cangshulun2()
