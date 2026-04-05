#!/usr/bin/env python3
"""
Simple test of database saving with Cyrillic names - minimal output
"""

import sqlite3

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
        "appearance": "стройная фигура",
        "clothing": "стильный чёрный костюм",
        "voice": "спокойная, холодная",
        "role": "главная героиня"
    }
]

print("Testing database save...")

for char_data in test_characters:
    name = char_data["name"]
    print(f"Saving character: {name}")
    
    cursor = conn.cursor()
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
    print("Saved")

conn.commit()

# Check what was saved
print("\nChecking saved characters...")
cursor = conn.cursor()
cursor.execute('SELECT id, name, description FROM characters')
rows = cursor.fetchall()

for row in rows:
    print(f"ID: {row[0]}, Name: '{row[1]}', Desc: {row[2][:30]}...")

conn.close()

print("\nTest complete")