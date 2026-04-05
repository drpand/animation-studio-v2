"""
Регенерация изображения для Сцены 1 с правильным промптом (частный самолёт).
"""
import asyncio, sys
sys.path.insert(0, '.')
from tools.kieai_tool import generate_image
import crud
from database import async_session
import httpx

# Получаем обновлённый final_prompt из БД
r = httpx.get('http://localhost:7860/api/orchestrator/scene-result/1/1/1', timeout=10)
d = r.json()
final_prompt = d.get('final_prompt', '')

print('=== FINAL PROMPT ===')
print(final_prompt)
print(f'Length: {len(final_prompt)} chars')
print()

async def gen():
    print('Generating image via Kie.ai...')
    result = await generate_image(prompt=final_prompt[:700], width=1024, height=1024)
    print()
    print('=== RESULT ===')
    print('status:', result.status)
    print('result_url:', getattr(result, 'result_url', 'N/A'))
    print('error:', getattr(result, 'error', 'N/A'))
    print('elapsed_ms:', getattr(result, 'elapsed_ms', 'N/A'))
    
    if result.status == 'success':
        async with async_session() as session:
            frames = await crud.get_scene_frames(session, 1, 1, 1)
            if frames:
                frames[0].image_url = result.result_url[:500]
                frames[0].status = 'approved'
                await session.commit()
                print()
                print('=== DB UPDATED ===')
                print('image_url:', result.result_url)
                print('status: approved')
    else:
        print('Generation failed:', getattr(result, 'error', 'unknown'))

asyncio.run(gen())
