#!/usr/bin/env python3
"""
Test scene pipeline for Scene 1
"""

import os
import sys
import asyncio

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

async def test_scene_pipeline():
    """Test running scene pipeline for scene 1"""
    
    from orchestrator.executor import run_scene_pipeline
    from database import async_session
    
    print("Testing Scene 1 pipeline...")
    
    # Get existing scene 1 text
    import sqlite3
    conn = sqlite3.connect('memory/studio.db')
    cursor = conn.cursor()
    cursor.execute('SELECT writer_text FROM scene_frames WHERE id = 1')
    row = cursor.fetchone()
    writer_text = row[0] if row else ""
    conn.close()
    
    if not writer_text:
        print("No writer text found for scene 1")
        return
    
    print(f"Found writer text ({len(writer_text)} chars)")
    print(f"Preview: {writer_text[:200]}...")
    
    # Run pipeline for scene 1
    print("\nRunning scene pipeline for Scene 1...")
    async with async_session() as db:
        try:
            result = await run_scene_pipeline(1, 1, 1, writer_text, db)
            print(f"Pipeline result: {result.get('status', 'unknown')}")
            print(f"Steps: {list(result.get('steps', {}).keys())}")
            
            # Check database after run
            conn = sqlite3.connect('memory/studio.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id, status, final_prompt, image_url FROM scene_frames WHERE scene_num = 1')
            frames = cursor.fetchall()
            print(f"\nScene 1 frames after pipeline:")
            for frame in frames:
                print(f"  ID: {frame[0]}, Status: {frame[1]}, Has prompt: {bool(frame[2])}, Has image: {bool(frame[3])}")
            conn.close()
            
        except Exception as e:
            print(f"Error running pipeline: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scene_pipeline())