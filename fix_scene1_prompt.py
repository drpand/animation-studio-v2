"""
Прямое обновление Сцены 1 — исправление промпта на частный самолёт.
"""
import asyncio, sys, json
sys.path.insert(0, '.')
from database import async_session
import crud

# Правильные данные для Сцены 1 (по сценарию "Родина 007")
WRITER_TEXT = """ИНТ. КАБИНА ЧАСТНОГО САМОЛЁТА. НОЧЬ.

Тесная кабина бизнес-джета. Кожаные кресла, приглушённый свет. За иллюминаторами — ночное небо над Гоа.

ЕВА (30-е) смотрит в маленький иллюминатор. Её лицо отражается в стекле — спокойное, но глаза выдают тревогу.

ГАРРИ (40-е) сидит напротив, листает журнал, но не читает — взгляд блуждает.

Звук двигателей — ровный, монотонный гул.

Ева замечает что-то за окном. Моргнула — показалось.

ГАРРИ
Что там?

ЕВА
Ничего... показалось.

Гарри откладывает журнал. Тишина между ними тяжелее гула двигателей."""

DOP_PROMPT = json.dumps({
    "shot": "Medium close-up, tight cabin framing, shallow depth of field, slight Dutch angle",
    "location": "Interior of private business jet cabin, luxury leather seats, small oval windows showing night sky, cramped intimate space, warm amber cabin lighting",
    "lighting": "Low-key warm amber cabin lights, cool blue moonlight from small windows, high contrast chiaroscuro on faces"
}, ensure_ascii=False)

ART_PROMPT = json.dumps({
    "style": "2.5D anime, Satoshi Kon psychological realism, hand-drawn 16mm film grain",
    "palette": "Warm amber interior, cool blue night outside, deep shadows, skin tones desaturated"
}, ensure_ascii=False)

SOUND_PROMPT = json.dumps({
    "mood": "Tense, intimate silence over constant engine drone, subtle anxiety"
}, ensure_ascii=False)

DIRECTOR_NOTES = """Камера давит — тесное пространство бизнес-джета усиливает клаустрофобию.
Крупные планы лиц, отражения в иллюминаторах.
Ритм медленный, тягучий — затишье перед бурей."""

async def update_scene():
    async with async_session() as session:
        frames = await crud.get_scene_frames(session, 1, 1, 1)
        if not frames:
            print("ERROR: Scene 1 not found")
            return
        
        frame = frames[0]
        frame.writer_text = WRITER_TEXT
        frame.director_notes = DIRECTOR_NOTES
        frame.dop_prompt = DOP_PROMPT
        frame.art_prompt = ART_PROMPT
        frame.sound_prompt = SOUND_PROMPT
        frame.final_prompt = (
            "Medium close-up, tight cabin framing, shallow depth of field, slight Dutch angle, "
            "Interior of private business jet cabin, luxury leather seats, small oval windows showing night sky, "
            "warm amber cabin lights, cool blue moonlight from small windows, high contrast chiaroscuro on faces, "
            "Tense, intimate silence over constant engine drone, subtle anxiety, "
            "2.5D anime, Satoshi Kon psychological realism, hand-drawn 16mm film grain, "
            "Warm amber interior, cool blue night outside, deep shadows, skin tones desaturated, "
            "no watermark, no text, no logos, correct anatomy, sharp focus"
        )
        frame.status = "in_review"
        frame.user_status = "pending"
        frame.image_url = ""
        
        await session.commit()
        print("Scene 1 updated with private jet data")
        print(f"  writer_text: {len(frame.writer_text)} chars")
        print(f"  final_prompt: {len(frame.final_prompt)} chars")
        print(f"  image_url cleared for regeneration")

asyncio.run(update_scene())
