import asyncio
import sys
import os
import json
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def test_auto_fix():
    from api.cv_check_api import cv_auto_fix
    from database import async_session

    class FakeReq:
        pass

    async with async_session() as db:
        result = await cv_auto_fix(3, db)
        print(json.dumps(result, indent=2, ensure_ascii=False))

asyncio.run(test_auto_fix())
