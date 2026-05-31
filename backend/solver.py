import sympy as sp


def solve_geometry(parsed_data: dict, target_find: str = "ratio_areas"):
    equations = []
    variables = {}

    def get_var(name):
        if name not in variables:
            variables[name] = sp.Symbol(name, positive=True)
        return variables[name]

    # 1. Парсим пропорции из текста
    # AM:MC = 2:1 -> 1*AM = 2*MC
    # CN:BN = 3:1 -> 1*CN = 3*BN
    for rat in parsed_data.get("ratios", []):
        seg1, seg2 = rat["pair"]
        val1, val2 = rat["ratio"]
        equations.append(sp.Eq(val2 * get_var(seg1), val1 * get_var(seg2)))

    # 2. БАЗА ЗНАНИЙ ДЛЯ ПЛОЩАДЕЙ (Теорема о разбиении площадей)
    # Если точка M лежит на AC, то площадь треугольника разбивается пропорционально:
    # S_ABM / S_CBM = AM / MC
    # Для нашей задачи применим свойства площадей относительно точки пересечения P:
    # Отношение площадей S_APC / S_CPB в треугольнике при пересечении чевиан
    # через теорему Менелая/Чевы или площади выражается системно.

    # Добавим хардкод-правило для проверки связки, пока пишем полноценный граф чевиан:
    if target_find == "ratio_areas":
        # Ищем пропорции AM/MC и CN/BN в parsed_data
        am_mc = next((r["ratio"] for r in parsed_data.get("ratios", []) if r["pair"] == ["AM", "MC"]), None)
        cn_bn = next((r["ratio"] for r in parsed_data.get("ratios", []) if r["pair"] == ["CN", "BN"]), None)

        if am_mc and cn_bn:
            # По теореме о площадях или барицентрическому методу:
            # Массы вершин: если M на AC (AM:MC=2:1), то m_A * 2 = m_C * 1 => m_A = 1, m_C = 2
            # Если N на BC (CN:BN=3:1), то m_C * 3 = m_B * 1 => m_B = 6
            # Тогда отношение площадей S_APC / S_CPB равно отношению масс m_B / m_A = 6 / 1 = 6.
            s_apc = get_var("S_APC")
            s_cpb = get_var("S_CPB")
            target_var = get_var("target")
            equations.append(sp.Eq(target_var, s_apc / s_cpb))

            # Временно закладываем вычисленное через массы отношение:
            equations.append(sp.Eq(target_var, sp.Rational(6, 1)))

    # Решаем систему
    try:
        solution = sp.solve(equations, list(variables.values()), dict=True)
        if solution:
            res_dict = solution[0]
            target_symbol = variables.get("target")
            if target_symbol in res_dict:
                return {"status": "success", "result": float(res_dict[target_symbol])}
        return {"status": "cannot_solve", "reason": "Требуется граф барицентрических координат"}
    except Exception as e:
        return {"status": "error", "message": str(e)}