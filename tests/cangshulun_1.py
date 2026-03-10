from vic3_analysis import production_table, ProductionAnalyzer


def test_cangshulun1():
    df_production_table = production_table()

    # 初始化
    optimizer = ProductionAnalyzer(df=df_production_table)

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
    for pm in banned_pms:
        optimizer.filter_by_production_method(pm)

    # 自动化全开，即最小化人数
    objective_vector = optimizer.employment_vector()

    # 约束条件
    constraints = []
    # 禁止进口
    constraints.append(optimizer.constraint_limit_import())
    # 以汽车为终端商品
    constraints.append(optimizer.constraint_produce("automobiles", 10e6 / 5200.0))
    # 全科技，相当于无限制
    # 染料采用合成厂制备，即禁止使用种植园制备染料
    constraints.append(
        optimizer.constraint_limit_building("building_dye_plantation", 0)
    )

    # 求解
    res = optimizer.linprog(objective_vector, constraints)

    print(res)

    print("GDP per capita (with throughput bonus):", res.gdp_per_capita() * 2.45)

    print("GDP per construction cost:", res.gdp / res.construction_cost)


if __name__ == "__main__":
    test_cangshulun1()
