#!/usr/bin/env python3
"""
Update Scene 1 and run image generation
"""

import sqlite3
import json
from datetime import datetime

# Connect to database
conn = sqlite3.connect('memory/studio.db')
cursor = conn.cursor()

# Get current scene 1 data
cursor.execute('SELECT final_prompt, status FROM scene_frames WHERE id = 1')
row = cursor.fetchone()

if row:
    final_prompt, status = row
    print(f"Current Scene 1 status: {status}")
    print(f"Final prompt exists: {bool(final_prompt)}")
    
    # Update status to 'pending' to trigger generation
    cursor.execute('UPDATE scene_frames SET status = ?, updated_at = ? WHERE id = 1', 
                   ('pending', datetime.now().isoformat()))
    conn.commit()
    print("Updated Scene 1 status to 'pending'")
    
    # Show what needs to be generated
    if final_prompt:
        print(f"\nPrompt for generation:")
        print("-" * 80)
        print(final_prompt[:500])
        print("..." if len(final_prompt) > 500 else "")
        print("-" * 80)
        
        # We need to trigger kie.ai generation
        # This would normally be done through the API or background task
        print("\nNote: Image generation would be triggered via Kie.ai API")
        print("The system is ready for Scene 1 image generation")
else:
    print("No Scene 1 found")

conn.close()

# Also update characters pattern in patterns.json
print("\nUpdating character patterns...")
import os
patterns_file = os.path.join('med_otdel', 'patterns.json')
if os.path.exists(patterns_file):
    with open(patterns_file, 'r', encoding='utf-8') as f:
        patterns = json.load(f)
    
    # Add or update character_consistency pattern
    character_pattern = None
    for i, pattern in enumerate(patterns.get('patterns', [])):
        if pattern.get('key') == 'character_consistency':
            character_pattern = pattern
            break
    
    if character_pattern:
        # Get all characters for pattern
        conn = sqlite3.connect('memory/studio.db')
        cursor = conn.cursor()
        cursor.execute('SELECT name, description FROM characters')
        characters = cursor.fetchall()
        conn.close()
        
        # Build pattern text
        pattern_text = "[RULE] При генерации изображений строго соблюдай внешность персонажей РОДИНА 007:\n"
        for name, desc in characters:
            pattern_text += f"- {name}: {desc}\n"
        
        character_pattern['rule_text'] = pattern_text[:2000]
        print(f"Updated character_consistency pattern with {len(characters)} characters")
    else:
        print("No character_consistency pattern found to update")

print("\nScene 1 pipeline ready for execution!")
print("Next step: Trigger image generation via API or background task")