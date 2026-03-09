from vic3_analysis import production_table, ProductionAnalyzer

def test_production_analysis():
    df_production_table = production_table()

    optimizer = ProductionAnalyzer(df=df_production_table)
    optimizer.goods_index()
    optimizer.production_index()
    optimizer.key_index()
    optimizer.profit_vector()
    optimizer.employment_vector()
    optimizer.construction_cost_vector()
    optimizer.era_vector()
    optimizer.find_same_buildings("building_iron_mine")
    optimizer.find_same_building_group("building_group_mine")

    constraints = []
    constraints.append(
        optimizer.constraint_limit_building("building_sugar_plantation", 0.1)
    )
    constraints.append(optimizer.constraint_limit_building("building_tea_plantation", 0.1))
    constraints.append(
        optimizer.constraint_limit_building("building_banana_plantation", 0.1)
    )
    constraints.append(
        optimizer.constraint_limit_building("building_rubber_plantation", 0.1)
    )
    constraints.append(
        optimizer.constraint_limit_building("building_tobacco_plantation", 0.1)
    )
    constraints.append(optimizer.constraint_limit_building("building_dye_plantation", 0.1))
    constraints.append(
        optimizer.constraint_limit_building("building_coffee_plantation", 0.1)
    )
    constraints.append(
        optimizer.constraint_limit_building("building_cotton_plantation", 0.1)
    )
    constraints.append(optimizer.constraint_limit_import())
    # constraints.append(optimizer.constraint_produce("automobiles", 100))
    constraints.append(optimizer.constraint_limit_construction_cost(10000))

    c = -optimizer.profit_vector()

    df = optimizer.linprog(c=c, inequality_constraints=constraints)
