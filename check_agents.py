import asyncio, sys
sys.path.insert(0, '.')
from database import async_session
import crud

async def check_agents():
    async with async_session() as db:
        agents = await crud.get_all_agents(db)
        for a in agents:
            print(f'{a.agent_id:20s} status={a.status:10s} model={a.model:40s} access={a.access_level}')
            if a.instructions:
                print(f'  instructions: {a.instructions[:100]}')

asyncio.run(check_agents())
