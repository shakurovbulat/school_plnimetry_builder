import json
import os
from parser import parse_geometry_text


def load_exercises():
    # Ищем файл exercises.json на один уровень выше или в текущей папке
    file_name = 'exercises.json'

    # Пытаемся найти файл в корне или в текущей папке
    if os.path.exists(file_name):
        path = file_name
    elif os.path.exists(os.path.join('..', file_name)):
        path = os.path.join('..', file_name)
    else:
        print(f"❌ Файл {file_name} не найден! Убедись, что он лежит в корне проекта.")
        return []

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get('exercises', [])


def run_tests():
    exercises = load_exercises()
    if not exercises:
        return

    print(f"🚀 Запуск тестирования парсера на {len(exercises)} задачах из учебника...\n")
    print("=" * 70)

    for idx, text in enumerate(exercises, 1):
        print(f"\n📝 Задача №{idx}:")
        print(f"Текст: \"{text}\"")

        # Прогоняем через наш парсер
        result = parse_geometry_text(text)

        # Красивый вывод результатов
        print("-" * 30)

        print(result)

        print("=" * 70)


if __name__ == "__main__":
    run_tests()