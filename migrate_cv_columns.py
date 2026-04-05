"""Миграция: добавить CV колонки в scene_frames."""
import asyncio, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from database import async_session
from sqlalchemy import text

async def main():
    async with async_session() as db:
        # Проверим существуют ли колонки
        result = await db.execute(text("PRAGMA table_info(scene_frames)"))
        columns = [r[1] for r in result.fetchall()]
        print("Existing columns:", columns)

        # Добавим cv_score
        if "cv_score" not in columns:
            await db.execute(text("ALTER TABLE scene_frames ADD COLUMN cv_score INTEGER DEFAULT 0"))
            print("✅ Added cv_score")
        else:
            print("cv_score already exists")

        # Добавим cv_description
        if "cv_description" not in columns:
            await db.execute(text("ALTER TABLE scene_frames ADD COLUMN cv_description TEXT DEFAULT ''"))
            print("✅ Added cv_description")
        else:
            print("cv_description already exists")

        # Добавим cv_details
        if "cv_details" not in columns:
            await db.execute(text("ALTER TABLE scene_frames ADD COLUMN cv_details TEXT DEFAULT ''"))
            print("✅ Added cv_details")
        else:
            print("cv_details already exists")

        await db.commit()
        print("✅ Migration complete!")

asyncio.run(main())
