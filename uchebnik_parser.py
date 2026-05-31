import fitz
import json

doc = fitz.open("merzlyak.pdf")
full_text = []
all_exersizes = []

for page in doc:
    full_text.append(page.get_text())


for page in full_text[55:70]:
    page65 = page.split("\n")
    edited_page65 = []
    is_behind_full = True
    exercises = []
    exercise = []

    for i, line in enumerate(page65):
        if line and line[-1] == '-' and i != len(page65) - 1:
            edited_page65.append(line[:-1] + page65[i + 1])
            is_behind_full = False
        elif line and is_behind_full and "Вариант" not in line and not line.isdigit():
            edited_page65.append(line)
        elif not is_behind_full:
            is_behind_full = True

    for i, line in enumerate(edited_page65):
        if line.split()[0][-1] == "." and line.split()[0][:-1].isdigit():
            if exercise:
                exercises.append(" ".join(exercise))
            exercise = []
            exercise.append(" ".join(line.split()))
        else:
            exercise.append(line)
    all_exersizes.extend(exercises)

for i in exercises:
    print(i)

all_exersizes = [" ".join(i.split()[1:]) for i in all_exersizes[1:]]
with open("exercises.json", "w", encoding="utf-8") as file:
    json.dump({"exercises": all_exersizes}, file)