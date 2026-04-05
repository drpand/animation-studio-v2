"""
Создание паттерна character_consistency для Art Director из карточек персонажей.
"""
import httpx, json, os

# Получаем всех персонажей из БД
r = httpx.get('http://localhost:7860/api/characters/', timeout=10)
data = r.json()
chars = data.get('characters', [])

print(f"Found {len(chars)} characters in DB")
print()

# Собираем описания для паттерна
char_descriptions = []
for c in chars:
    char_descriptions.append(f"- {c['name']}: {c['description']}")

pattern_text = "[RULE] При генерации изображений строго соблюдай внешность персонажей:\n" + "\n".join(char_descriptions)

print("=== CHARACTER CONSISTENCY PATTERN ===")
print(pattern_text[:500])
print()

# Сохраняем в patterns.json
patterns_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "med_otdel", "patterns.json")

if os.path.exists(patterns_file):
    with open(patterns_file, "r", encoding="utf-8") as f:
        patterns_data = json.load(f)
else:
    patterns_data = {"patterns": []}

patterns = patterns_data.get("patterns", [])

# Удаляем старый character_consistency если есть
patterns = [p for p in patterns if p.get("key") != "character_consistency"]

# Добавляем новый
patterns.append({
    "key": "character_consistency",
    "name": "Единообразие персонажей",
    "rule_text": pattern_text,
    "description": "Автоматически создано HR при кастинге — РОДИНА 007",
    "category": "visual",
    "priority": 100,
})

patterns_data["patterns"] = patterns

with open(patterns_file, "w", encoding="utf-8") as f:
    json.dump(patterns_data, f, ensure_ascii=False, indent=2)

print(f"Pattern saved to {patterns_file}")
print(f"Total patterns: {len(patterns)}")
