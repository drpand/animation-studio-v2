#!/usr/bin/env python3
"""
Simple test of database saving with Cyrillic names
"""

import sqlite3
import json

# Connect to database
conn = sqlite3.connect('memory/studio.db')

# Clear table first
conn.execute('DELETE FROM characters')
conn.commit()

# Test data with Cyrillic names
test_characters = [
    {
        "name": "Ева",
        "age": "25-30", 
        "appearance": "стройная фигура, короткие тёмные волосы",
        "clothing": "стильный чёрный костюм",
        "voice": "спокойная, холодная",
        "role": "главная героиня"
    },
    {
        "name": "Гарри",
        "age": "35-45",
        "appearance": "крупное телосложение, короткая седая щетина",
        "clothing": "практичная куртка",
        "voice": "твёрдый, уверенный",
        "role": "главный герой наставник"
    }
]

print("Testing database save with Cyrillic names...\n")

for char_data in test_characters:
    name = char_data["name"]
    print(f"Saving character: {repr(name)}")
    print(f"Name bytes: {name.encode('utf-8')}")
    print(f"Name hex: {name.encode('utf-8').hex()}")
    
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO characters (project_id, name, description, voice_id, relations, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            1,
            name,
            f"Возраст: {char_data['age']}. Внешность: {char_data['appearance']}. Одежда: {char_data['clothing']}. Голос: {char_data['voice']}",
            char_data["voice"],
            char_data["role"],
            "2026-04-05T22:37:49.462072"
        ))
        print(f"  ✓ Saved successfully!")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    print()

conn.commit()

# Check what was saved
print("\nChecking saved characters...")
cursor = conn.cursor()
cursor.execute('SELECT id, name, description FROM characters')
rows = cursor.fetchall()

for row in rows:
    print(f"ID: {row[0]}")
    print(f"  Name: {repr(row[1])}")
    print(f"  Name hex: {row[1].encode('utf-8').hex() if row[1] else 'EMPTY'}")
    print(f"  Desc preview: {row[2][:50]}...")
    print()

conn.close()

print("\nNow testing the _extract_json_array function...")
from orchestrator.executor import _extract_json_array

# Test JSON extraction
sample_json = '[{"name": "Ева", "age": "25-30"}, {"name": "Гарри", "age": "35-45"}]'
print(f"Sample JSON: {sample_json}")
characters = _extract_json_array(sample_json)
print(f"Extracted {len(characters)} characters:")
for char in characters:
    print(f"  Name: {repr(char.get('name', ''))}, Type: {type(char.get('name', ''))}")