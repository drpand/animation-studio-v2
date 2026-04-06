import httpx
import asyncio
import json

async def test_cv():
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            'http://localhost:7860/api/tools/cv-check',
            json={'frame_id': 3, 'model': 'google/gemini-3.1-flash-lite-preview'}
        )
        print(f"Status: {r.status_code}")
        print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}")

asyncio.run(test_cv())
