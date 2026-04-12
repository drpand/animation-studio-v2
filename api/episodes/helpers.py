"""Shared helpers for episodes API endpoints."""
from datetime import datetime

import crud
from database import Season


async def get_active_project_id(db):
    """Get the ID of the active project."""
    project = await crud.get_active_project(db)
    return project.id if project else None


async def get_active_project(db):
    """Get the active project object."""
    return await crud.get_active_project(db)


async def get_season_by_number(db, project_id, season_num):
    """Get or create a season by its number."""
    seasons = await crud.get_seasons(db, project_id)
    for s in seasons:
        if s.season_number == season_num:
            return s
    return None


async def ensure_season(db, project_id, season_num):
    """Ensure a season exists, create if not."""
    season = await get_season_by_number(db, project_id, season_num)
    if not season:
        season_data = {
            "project_id": project_id,
            "season_number": season_num,
            "title": f"Сезон {season_num}",
            "description": "",
        }
        season_obj = Season(**season_data)
        db.add(season_obj)
        await db.commit()
        await db.refresh(season_obj)
        season = season_obj
    return season


async def get_episode_by_number(db, season_id, ep_num):
    """Get an episode by its number within a season."""
    return await crud.get_episode(db, season_id, ep_num)


def now_iso():
    """Return current datetime as ISO string."""
    return datetime.now().isoformat()
