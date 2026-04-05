import asyncio, sys, httpx
sys.path.insert(0, '.')
from tools.kieai_tool import generate_image
import crud
from database import async_session

r = httpx.get('http://localhost:7860/api/orchestrator/scene-result/1/1/1', timeout=10)
d = r.json()
final_prompt = d.get('final_prompt', '')
final_prompt = final_prompt.replace('пассажирского', 'частного').replace('пассажирск', 'частн')

print('Prompt:', final_prompt[:200])
print('Prompt length:', len(final_prompt))

async def gen():
    result = await generate_image(prompt=final_prompt[:700], width=1024, height=1024)
    print('status:', result.status)
    print('result_url:', getattr(result, 'result_url', 'N/A'))
    print('error:', getattr(result, 'error', 'N/A'))
    print('elapsed_ms:', getattr(result, 'elapsed_ms', 'N/A'))
    if result.status == 'success':
        async with async_session() as session:
            frames = await crud.get_scene_frames(session, 1, 1, 1)
            if frames:
                frames[0].image_url = result.result_url[:500]
                await session.commit()
                print('DB updated with new image')
                print('image_url:', result.result_url)

asyncio.run(gen())
