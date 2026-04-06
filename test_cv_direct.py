import asyncio
import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Прямой вызов endpoint без HTTP
async def test_direct():
    from api.cv_check_api import cv_check
    from database import async_session
    from pydantic import BaseModel

    class FakeReq:
        frame_id = 3
        model = "google/gemini-3.1-flash-lite-preview"

    async with async_session() as db:
        result = await cv_check(FakeReq(), db)
        print(f"Result: {result}")

asyncio.run(test_direct())
