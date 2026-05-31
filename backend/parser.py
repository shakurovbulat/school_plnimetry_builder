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
    'параллелограмм', 'треугольник', 'ромб', 'трапеция', 'прямоугольник', 'квадрат', 'окружность', 'четырехугольник'
])
SHAPE_MODIFIERS = morph_pipeline([
    'прямоугольный', 'равнобокий', 'равнобедренный', 'равносторонний', 'выпуклый', 'остроугольный'
])
SEGMENT_KEYWORDS = morph_pipeline([
    'отрезок', 'сторона', 'прямая', 'диагональ', 'биссектриса', 'перпендикуляр', 'диаметр', 'радиус', 'медиана',
    'высота'
])
EQUAL_KEYWORDS = morph_pipeline(['равен', 'равна', 'равно', 'составляет', 'равны', '=', '=='])

ANGLE_SIGN = rule(custom(lambda token: token == '∠'))
ANGLE_WORD = morph_pipeline(['угол'])
ANGLE_KEYWORDS = or_(ANGLE_WORD, ANGLE_SIGN)

# --- ГРАММАТИКА YARGY ---

# 1. Фигуры с именами и без
SHAPE_RULE = rule(SHAPE_MODIFIERS.optional(), SHAPE_KEYWORDS, or_(QUAD_NAME, TRIANGLE_NAME).optional())

# 2. Строгое правило для пропорций: "BM : MC = 3 : 4"
COLON = rule(custom(lambda token: token == ':'))
RATIO_RULE = rule(
    SEGMENT_NAME, COLON, SEGMENT_NAME,
    EQUAL_KEYWORDS,
    IS_NUM, COLON, IS_NUM
)

# 3. Отрезок с конкретной длиной: "AB = 12"
SEGMENT_LENGTH_RULE = rule(
    SEGMENT_KEYWORDS.optional(),
    SEGMENT_NAME,
    EQUAL_KEYWORDS,
    IS_NUM
)

# 4. Просто упоминание отрезка или линии: "медианы AM и BK"
SEGMENT_MENTION_RULE = rule(
    SEGMENT_KEYWORDS,
    SEGMENT_NAME
)

# 5. Углы и точки
ANGLE_RULE = rule(ANGLE_KEYWORDS, TRIANGLE_NAME)
POINT_RULE = rule(morph_pipeline(['точка', 'точки']).optional(), POINT_NAME)

# Инициализация парсеров
ratio_parser = Parser(RATIO_RULE)
shape_parser = Parser(SHAPE_RULE)
segment_length_parser = Parser(SEGMENT_LENGTH_RULE)
segment_mention_parser = Parser(SEGMENT_MENTION_RULE)
angle_parser = Parser(ANGLE_RULE)
point_parser = Parser(POINT_RULE)


def clean_input_text(text: str) -> str:
    """ Глубокая очистка текста от мусора, ломающего токенизацию """
    # 1. Убираем ссылки на рисунки, тесты, контрольные
    text = re.sub(r'(?i)на рисунке\s+\d+', '', text)
    text = re.sub(r'(?i)рис\.\s+\d+', '', text)
    text = re.sub(r'(?i)контрольная\s+работа\s+№\s+\d+', '', text)
    text = re.sub(r'(?i)работа\s+№\s+\d+', '', text)
    text = re.sub(r'(?i)тема\.', '', text)

    # 2. Исправляем опечатку распознавания: русская 'В' вместо латинской 'B' внутри обозначений (4ВK -> 4 BK)
    text = re.sub(r'(\d+)В([A-Z])', r'\1 B\2', text)
    text = re.sub(r'\bВ([A-Z]{1,3})\b', r'B\1', text)

    # 3. Убираем единицы измерения, чтобы они не прилипали к числам (48 см -> 48)
    text = re.sub(r'\b(см|дм|м|мм|°|градус[аов]*|см²)\b', '', text)

    # 4. Заменяем странные символы равенства из PDF (например, ) на нормальный знак =
    text = re.sub(r'[^\x00-\x7FА-Яа-я∠=:]', ' = ', text)

    return text


def parse_geometry_text(text: str):
    clean_text = clean_input_text(text)

    extracted_data = {
        "points": [],
        "shapes": [],
        "segments": [],
        "ratios": [],
        "angles": []
    }

    # Вспомогательная функция для безопасного добавления уникальных точек
    def add_points(name_str):
        for char in name_str:
            if char.isalpha() and char.isupper() and char not in extracted_data["points"]:
                if ord(char) < 128:  # Только латиница
                    extracted_data["points"].append(char)

    # 1. Сначала вытаскиваем пропорции динамически (БЕЗ ХАРДКОДА ИНДЕКСОВ)
    spans_to_delete = []
    for match in ratio_parser.findall(clean_text):
        found_segments = []
        found_numbers = []

        for fact in match.tokens:
            val = fact.value
            # Если это имя отрезка (2 заглавные латинские буквы)
            if val.isalpha() and len(val) == 2 and val.isupper():
                found_segments.append(val.upper())
            # Если это число
            elif val.isdigit():
                found_numbers.append(int(val))

        # Заносим данные, только если нашли ровно 2 отрезка и 2 числа для пропорции
        if len(found_segments) == 2 and len(found_numbers) == 2:
            extracted_data["ratios"].append({
                "pair": found_segments,
                "ratio": found_numbers
            })
            for seg in found_segments:
                add_points(seg)

        spans_to_delete.append(match.span)

    # Вырезаем пропорции с конца, используя .start и .stop
    for span in sorted(spans_to_delete, key=lambda x: x.start, reverse=True):
        clean_text = clean_text[:span.start] + " " * (span.stop - span.start) + clean_text[span.stop:]

    # 2. Ищем фигуры
    for match in shape_parser.findall(clean_text):
        tokens = [fact.value for fact in match.tokens]
        shape_type = tokens[-1].lower() if not tokens[-1].isupper() else tokens[-2].lower()
        shape_name = tokens[-1].upper() if tokens[-1].isupper() else "ANON"

        if not any(s["name"] == shape_name and s["type"] == shape_type for s in extracted_data["shapes"]):
            extracted_data["shapes"].append({"type": shape_type, "name": shape_name})
        if shape_name != "ANON":
            add_points(shape_name)

    # 3. Ищем отрезки С ДЛИНАМИ
    for match in segment_length_parser.findall(clean_text):
        tokens = [fact.value for fact in match.tokens]
        seg_name = tokens[-3].upper()
        try:
            length_val = int(tokens[-1])
            if not any(s["name"] == seg_name for s in extracted_data["segments"]):
                extracted_data["segments"].append({"name": seg_name, "length": length_val})
            add_points(seg_name)
        except ValueError:
            continue

    # 4. Добираем отрезки, которые ПРОСТО УПОМЯНУТЫ
    for match in segment_mention_parser.findall(clean_text):
        tokens = [fact.value for fact in match.tokens]
        seg_name = tokens[-1].upper()
        if not any(s["name"] == seg_name for s in extracted_data["segments"]):
            extracted_data["segments"].append({"name": seg_name, "length": None})
        add_points(seg_name)

    # 5. Ищем углы
    for match in angle_parser.findall(clean_text):
        tokens = [fact.value for fact in match.tokens]
        angle_name = tokens[-1].upper()
        if angle_name not in extracted_data["angles"]:
            extracted_data["angles"].append(angle_name)
        add_points(angle_name)

    # 6. Добираем одиночные точки
    for match in point_parser.findall(clean_text):
        tokens = [fact.value for fact in match.tokens]
        p_name = tokens[-1].upper()
        if len(p_name) == 1 and ord(p_name) < 128:
            if p_name not in extracted_data["points"]:
                extracted_data["points"].append(p_name)

    return extracted_data


if __name__ == "__main__":
    tasks = [
        "На диагонали BD параллелограмма ABCD отметили точки M и K так, что ∠BAM = ∠DCK (точка M лежит между точками B и K). Докажите, что BM = DK.",
        "Биссектриса угла D параллелограмма ABCD пересекает сторону BC в точке M, BM:MC=3:4. Найдите периметр параллелограмма, если BC = 28 см.",
        "Основания равнобокой трапеции равны 12 см и 18 см, а диагональ является биссектрисой её острого угла. Вычислите площадь трапеции."
    ]

    import pprint

    for i, task in enumerate(tasks, 1):
        print(f"\n--- Тест {i} ---")
        pprint.pprint(parse_geometry_text(task))