"""
HR Casting — создание карточек персонажей из сценария "Родина 007".
"""
import httpx, json, time

API = "http://localhost:7860/api/characters/"

characters = [
    {
        "name": "Ева",
        "age": 18,
        "appearance": "длинные прямые тёмные волосы, огромные синие глаза, точный контур лица",
        "clothing": "синяя форма английского колледжа, белая рубашка, герб на нагрудном кармане",
        "speech": "спокойная, говорит по-английски и по-русски",
        "voice_id": "calm young female, bilingual EN/RU",
        "relations": "главная героиня, дочь",
        "kieai_description": "18-year-old girl, long straight dark hair, huge blue eyes, precise facial contour, wearing blue English college uniform with white shirt and badge on chest pocket"
    },
    {
        "name": "Гарри",
        "age": 45,
        "appearance": "мужчина средних лет, усталое лицо, внимательный взгляд",
        "clothing": "повседневная одежда пассажира",
        "speech": "тихий, задумчивый, говорит мало",
        "voice_id": "middle-aged male, calm, thoughtful",
        "relations": "спутник Евы в самолёте",
        "kieai_description": "45-year-old man, tired face, attentive gaze, wearing casual passenger clothing, sitting in airplane seat"
    },
    {
        "name": "Мама",
        "age": 40,
        "appearance": "женщина средних лет, встревоженное лицо",
        "clothing": "повседневная одежда",
        "speech": "эмоциональная, кричит, плачет",
        "voice_id": "middle-aged female, emotional",
        "relations": "мать Евы",
        "kieai_description": "40-year-old woman, worried face, everyday clothing, emotional expression"
    },
    {
        "name": "Папа",
        "age": 45,
        "appearance": "мужчина средних лет, строгий, авторитетный",
        "clothing": "повседневная мужская одежда",
        "speech": "твёрдый, командный тон",
        "voice_id": "middle-aged male, authoritative",
        "relations": "отец Евы",
        "kieai_description": "45-year-old man, strict authoritative look, everyday male clothing"
    },
    {
        "name": "Мистер Джонс",
        "age": 50,
        "appearance": "пожилой мужчина, седые волосы, представительный",
        "clothing": "деловой костюм",
        "speech": "вежливый, официальный тон",
        "voice_id": "older male, polite, formal",
        "relations": "знакомый семьи",
        "kieai_description": "50-year-old man, grey hair, distinguished appearance, wearing business suit"
    },
    {
        "name": "Ангелина",
        "age": 18,
        "appearance": "девушка, яркая внешность",
        "clothing": "модная молодёжная одежда",
        "speech": "громкая, энергичная",
        "voice_id": "young female, loud, energetic",
        "relations": "подруга Евы",
        "kieai_description": "18-year-old girl, bright appearance, wearing fashionable youth clothing"
    },
    {
        "name": "Милена",
        "age": 18,
        "appearance": "девушка, привлекательная",
        "clothing": "стильная одежда",
        "speech": "уверенная, иногда агрессивная",
        "voice_id": "young female, confident",
        "relations": "соперница Евы",
        "kieai_description": "18-year-old girl, attractive, wearing stylish clothing, confident expression"
    },
    {
        "name": "Джек",
        "age": 20,
        "appearance": "молодой парень, спортивный",
        "clothing": "повседневная молодёжная одежда",
        "speech": "грубоватый, простой",
        "voice_id": "young male, rough, simple",
        "relations": "знакомый Милены",
        "kieai_description": "20-year-old guy, athletic build, wearing casual youth clothing"
    },
    {
        "name": "Том",
        "age": 20,
        "appearance": "молодой парень",
        "clothing": "повседневная одежда",
        "speech": "поддерживающий Джека",
        "voice_id": "young male, supportive",
        "relations": "друг Джека",
        "kieai_description": "20-year-old guy, everyday clothing, supporting friend"
    },
    {
        "name": "Агент",
        "age": 35,
        "appearance": "мужчина, строгий, неприметная внешность",
        "clothing": "тёмный костюм, наушник",
        "speech": "сухой, командный",
        "voice_id": "male, dry, commanding",
        "relations": "агент спецслужб",
        "kieai_description": "35-year-old man, strict unremarkable appearance, wearing dark suit with earpiece, secret agent"
    },
]

print("=== HR CASTING: РОДИНА 007 ===")
print(f"Creating {len(characters)} character cards...\n")

for i, char in enumerate(characters, 1):
    r = httpx.post(API, json=char, timeout=10)
    data = r.json()
    status = "OK" if data.get("ok") else "FAIL"
    print(f"{i:2d}. [{status}] {char['name']:15s} age={char['age']:3d}  kieai_desc={char['kieai_description'][:60]}...")
    time.sleep(0.3)

print(f"\n=== Casting complete: {len(characters)} characters created ===")

# Verify
r2 = httpx.get(API, timeout=10)
data2 = r2.json()
chars = data2.get("characters", [])
print(f"\n=== DB verification: {len(chars)} characters ===")
for c in chars:
    print(f"  ID={c['id']:3d}  {c['name']:15s}  {c['description'][:80]}")
