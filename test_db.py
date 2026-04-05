import asyncio, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from database import async_session
import crud

async def main():
    async with async_session() as db:
        # Проверим что таблицы существуют
        from sqlalchemy import text
        result = await db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [r[0] for r in result.fetchall()]
        print("Tables:", tables)

        # Проверим scene_frames
        if "scene_frames" in tables:
            frames = await crud.get_all_scene_frames(db)
            print(f"Frames count: {len(frames)}")

            # Протестируем CV check endpoint напрямую
            if frames:
                frame = frames[0]
                print(f"Frame {frame.id}: cv_score={frame.cv_score}, image_url={frame.image_url[:50] if frame.image_url else 'none'}")

asyncio.run(main())
