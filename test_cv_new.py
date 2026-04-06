import asyncio
import json
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def test_cv_new():
    from api.cv_check_api import _run_cv_check
    from database import async_session

    class FakeFrame:
        id = 3
        image_url = "/tools_cache/kie_8171f5fc5e3d24588142cf92f618b310.png"
        writer_text = "СЦЕНА 3: ИСКАЖЕНИЕ РЕАЛЬНОСТИ (25 сек). Отражение тени самурая в лезвии меча, красная луна, искажение реальности, хроматическая аберрация."

    async with async_session() as db:
        frame = FakeFrame()
        result = await _run_cv_check(frame, frame.writer_text, "google/gemini-3.1-flash-lite-preview")
        print(json.dumps(result, indent=2, ensure_ascii=False))

asyncio.run(test_cv_new())
