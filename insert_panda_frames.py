"""Вставляет 4 кадра панды-самурая в БД для теста storyboard."""
import asyncio
import json
import os
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import async_session
import crud

FRAMES = [
    {
        "season_num": 1, "episode_num": 1, "scene_num": 1, "frame_num": 1,
        "status": "approved",
        "writer_text": "СЦЕНА 1: ТИШИНА ПРЕДУПРЕЖДЕНИЯ (20 сек). Панда сидит в позе seiza в ночном храме, луна освещает половину лица.",
        "final_prompt": "2.5D anime, hyper-detailed, Satoshi Kon aesthetic, cinematic. Wide shot, interior of minimalist cyberpunk temple. Panda samurai in traditional hakama sits in perfect seiza posture on tatami. Moonlight from large circular window cuts through darkness, illuminating only half of his face and torso. Strong chiaroscuro.",
        "image_url": "/tools_cache/kie_f5443b07f348e994a5ac1e8a0781b9ee.png",
        "critic_feedback": "",
    },
    {
        "season_num": 1, "episode_num": 1, "scene_num": 2, "frame_num": 1,
        "status": "approved",
        "writer_text": "СЦЕНА 2: ПРОЦЕСС ОБНАЖЕНИЯ (20 сек). Панда точит меч точильным камнем, крупные планы рук, искры.",
        "final_prompt": "2.5D anime, photorealistic textures, Satoshi Kon dynamic framing. Extreme close-up shot. Powerful fur-covered panda hands meticulously sharpening a katana blade with traditional whetstone. Sparks of orange and blue fly from point of contact.",
        "image_url": "/tools_cache/kie_20a4e583666a171009cae65ac2cf76d6.png",
        "critic_feedback": "",
    },
    {
        "season_num": 1, "episode_num": 1, "scene_num": 3, "frame_num": 1,
        "status": "approved",
        "writer_text": "СЦЕНА 3: ИСКАЖЕНИЕ РЕАЛЬНОСТИ (25 сек). Отражение тени самурая в лезвии меча, красная луна.",
        "final_prompt": "2.5D anime, distorted reality, chromatic aberration, Satoshi Kon psychological horror influence. POV from blade surface. Highly polished katana acts as warped mirror. Reflected in it is distorted menacing shadow-figure of samurai without face.",
        "image_url": "/tools_cache/kie_8171f5fc5e3d24588142cf92f618b310.png",
        "critic_feedback": "",
    },
    {
        "season_num": 1, "episode_num": 1, "scene_num": 4, "frame_num": 1,
        "status": "approved",
        "writer_text": "СЦЕНА 4: ОСОЗНАНИЕ И ВЫБОР (15 сек). Панда поднимает меч проверяя лезвие, микротрещина на кончике.",
        "final_prompt": "2.5D anime, dramatic angle, hyper-detailed material rendering. Low-angle shot. Panda samurai stands holding katana vertically in front of his face inspecting edge against moonlight. Moon directly behind blade creating powerful backlight.",
        "image_url": "/tools_cache/kie_a22f958e3797d9d8b1198baa3cc03fd4.png",
        "critic_feedback": "",
    },
]

async def main():
    async with async_session() as db:
        for frame_data in FRAMES:
            frame_data["created_at"] = datetime.now().isoformat()
            frame_data["updated_at"] = datetime.now().isoformat()
            frame = await crud.create_scene_frame(db, frame_data)
            print(f"✅ Кадр {frame_data['scene_num']} создан (ID: {frame.id})")
        await db.commit()
    print("✅ Все 4 кадра сохранены в БД!")

asyncio.run(main())
