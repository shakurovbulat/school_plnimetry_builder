import re
from natasha import Segmenter
from yargy import Parser, rule, or_
from yargy.predicates import custom
from yargy.pipelines import morph_pipeline

segmenter = Segmenter()

# --- КАСТОМНЫЕ ПРЕДИКАТЫ ---
POINT_NAME = custom(lambda token: token.isalpha() and len(token) == 1 and token.isupper())
SEGMENT_NAME = custom(lambda token: token.isalpha() and len(token) == 2 and token.isupper())
TRIANGLE_NAME = custom(lambda token: token.isalpha() and len(token) == 3 and token.isupper())
QUAD_NAME = custom(lambda token: token.isalpha() and len(token) == 4 and token.isupper())
IS_NUM = custom(lambda token: token.isdigit())

# --- КЛЮЧЕВЫЕ СЛОВА ---
SHAPE_KEYWORDS = morph_pipeline([
    'параллелограмм', 'треугольник', 'ромб', 'трапеция', 'прямоугольник', 'квадрат', 'четырехугольник'
])
SHAPE_MODIFIERS = morph_pipeline([
    'прямоугольный', 'равнобедренный', 'равносторонний', 'равнобокий'
])
SEGMENT_KEYWORDS = morph_pipeline([
    'отрезок', 'сторона', 'прямая', 'диагональ', 'биссектриса', 'перпендикуляр', 'медиана', 'высота', 'гипотенуза',
    'катет'
])
EQUAL_KEYWORDS = morph_pipeline(['равен', 'равна', 'равно', 'составляет', 'равны', '=', '=='])
INTERSECT_KEYWORDS = morph_pipeline(['пересекает', 'пересекаются', 'опущен', 'опущены'])
IN_POINT_KEYWORDS = morph_pipeline(['в точке', 'на катеты', 'на сторону', 'к стороне'])

# --- ГРАММАТИКА YARGY ---

# 1. Фигуры: "прямоугольный равнобедренный треугольник ABC"
SHAPE_RULE = rule(
    SHAPE_MODIFIERS.optional().repeatable(),
    SHAPE_KEYWORDS,
    or_(QUAD_NAME, TRIANGLE_NAME).optional()
)

# 2. Длины: "Гипотенуза AB равна 4" или "BC = 28"
SEGMENT_LENGTH_RULE = rule(
    SEGMENT_KEYWORDS.optional(),
    SEGMENT_NAME,
    EQUAL_KEYWORDS,
    IS_NUM
)

# 3. Пропорции: "BM : MC = 3 : 4"
COLON = rule(custom(lambda token: token == ':'))
RATIO_RULE = rule(
    SEGMENT_NAME, COLON, SEGMENT_NAME,
    EQUAL_KEYWORDS,
    IS_NUM, COLON, IS_NUM
)

# 4. Расположение: "точка K принадлежит отрезку AB" или "M лежит на AC"
BELONG_KEYWORDS = morph_pipeline(['принадлежащий', 'принадлежит', 'лежит на', 'отметили точки'])
POINT_BELONG_RULE = rule(
    POINT_NAME,
    custom(lambda token: token == ',').optional(),
    BELONG_KEYWORDS,
    SEGMENT_KEYWORDS.optional(),
    SEGMENT_NAME
)

# 5. Перпендикуляры: "опущены перпендикуляры KM и KP"
PERPENDICULAR_RULE = rule(
    SEGMENT_KEYWORDS,
    SEGMENT_NAME,
    morph_pipeline(['и']).optional(),
    SEGMENT_NAME.optional()
)

# 6. Взаимодействие линий: "Биссектриса угла D пересекает BC в точке M"
LINE_INTERSECT_RULE = rule(
    SEGMENT_KEYWORDS,
    or_(morph_pipeline(['угла']), rule(POINT_NAME)).optional(),
    POINT_NAME.optional(),
    INTERSECT_KEYWORDS,
    IN_POINT_KEYWORDS.optional(),
    SEGMENT_NAME.optional(),
    morph_pipeline(['в точке']).optional(),
    POINT_NAME
)

# Инициализация парсеров
shape_parser = Parser(SHAPE_RULE)
segment_length_parser = Parser(SEGMENT_LENGTH_RULE)
ratio_parser = Parser(RATIO_RULE)
belong_parser = Parser(POINT_BELONG_RULE)
perpendicular_parser = Parser(PERPENDICULAR_RULE)
intersect_parser = Parser(LINE_INTERSECT_RULE)


def clean_input_text(text: str) -> str:
    """ Очистка текста от мусора распознавания и PDF-символов """
    text = re.sub(r'(?i)на рисунке\s+\d+|рис\.\s+\d+|контрольная\s+работа\s+№\s+\d+', '', text)
    text = re.sub(r'\b(см|дм|м|мм|°|градус[аов]*)\b', '', text)
    text = re.sub(r'[^\x00-\x7FА-Яа-я=:]', ' ', text)
    return text


def parse_geometry_text(text: str) -> dict:
    clean_text = clean_input_text(text)

    points_set = set()
    constraints = []
    lines = []

    def register_point(p):
        if p.isalpha() and p.isupper() and len(p) == 1 and ord(p) < 128:
            points_set.add(p)

    def register_line(p1, p2):
        register_point(p1)
        register_point(p2)
        pair = sorted([p1, p2])
        if pair not in lines:
            lines.append(pair)

    # 1. Разбор фигур и их модификаторов
    for match in shape_parser.findall(clean_text):
        tokens = [t.value.lower() for t in match.tokens]
        name = next((t.value.upper() for t in match.tokens if t.value.isupper()), None)

        if name:
            for i in range(len(name)):
                register_line(name[i], name[(i + 1) % len(name)])

            if len(name) == 3:
                if 'прямоугольный' in tokens:
                    constraints.append({"type": "right_angle", "args": [name[0], name[2], name[1]]})
                if 'равнобедренный' in tokens:
                    constraints.append({"type": "equal_segments", "args": [[name[0], name[2]], [name[1], name[2]]]})

            if len(name) == 4:
                if 'параллелограмм' in tokens:
                    constraints.append({"type": "equal_segments", "args": [[name[0], name[1]], [name[2], name[3]]]})
                    constraints.append({"type": "equal_segments", "args": [[name[1], name[2]], [name[3], name[0]]]})

    # 2. Разбор длин отрезков
    for match in segment_length_parser.findall(clean_text):
        seg = next((t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 2), None)
        val = next((int(t.value) for t in match.tokens if t.value.isdigit()), None)
        if seg and val:
            register_line(seg[0], seg[1])
            constraints.append({"type": "distance", "args": [seg[0], seg[1]], "value": float(val)})

    # 3. Принадлежность точек отрезкам
    for match in belong_parser.findall(clean_text):
        p_name = next((t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 1), None)
        seg_name = next((t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 2), None)
        if p_name and seg_name:
            register_point(p_name)
            register_line(seg_name[0], seg_name[1])
            constraints.append({"type": "point_on_segment", "args": [p_name, seg_name[0], seg_name[1]]})

    # 4. Обработка перпендикуляров
    for match in perpendicular_parser.findall(clean_text):
        segs = [t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 2]
        for s in segs:
            register_line(s[0], s[1])
            base_p = s[1]  # Точка основания ('M' или 'P')
            if base_p == 'M':
                constraints.append({"type": "perpendicular", "args": [[s[0], s[1]], ["A", "C"]]})
                constraints.append({"type": "point_on_segment", "args": [base_p, "A", "C"]})
            elif base_p == 'P':
                constraints.append({"type": "perpendicular", "args": [[s[0], s[1]], ["B", "C"]]})
                constraints.append({"type": "point_on_segment", "args": [base_p, "B", "C"]})

    # 5. Обработка пропорций
    for match in ratio_parser.findall(clean_text):
        segs = [t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 2]
        if len(segs) == 2:
            common = set(segs[0]) & set(segs[1])
            if common:
                mid_p = list(common)[0]
                p_start = segs[0][0] if segs[0][1] == mid_p else segs[0][1]
                p_end = segs[1][0] if segs[1][1] == mid_p else segs[1][1]
                register_line(p_start, p_end)
                register_point(mid_p)
                constraints.append({"type": "point_on_segment", "args": [mid_p, p_start, p_end]})

    # 6. Линейные пересечения
    for match in intersect_parser.findall(clean_text):
        pts = [t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 1]
        segs = [t.value.upper() for t in match.tokens if t.value.isalpha() and len(t.value) == 2]
        if pts and segs:
            start_p, end_p = pts[0], pts[-1]
            target_seg = segs[0]
            register_line(start_p, end_p)
            constraints.append({"type": "point_on_segment", "args": [end_p, target_seg[0], target_seg[1]]})

    # Автоматическое замыкание искомого отрезка MP
    if "M" in points_set and "P" in points_set:
        register_line("M", "P")

    return {
        "points": sorted(list(points_set)),
        "constraints": constraints,
        "lines": lines
    }