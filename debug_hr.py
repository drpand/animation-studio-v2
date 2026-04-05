#!/usr/bin/env python3
"""
Debug script to see what HR agent returns and test saving
"""

import os
import sys
import asyncio
import json
from pypdf import PdfReader

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator.executor import _extract_json_array

async def debug_hr_json():
    """Debug HR JSON extraction"""
    
    # Find the PDF file
    scripts_dir = os.path.join(project_root, "memory", "scripts")
    pdf_files = [f for f in os.listdir(scripts_dir) if f.endswith('.pdf') and 'Родина' in f]
    
    if not pdf_files:
        print("No Родина 007 PDF file found")
        return
        
    pdf_filename = pdf_files[0]
    pdf_path = os.path.join(scripts_dir, pdf_filename)
    
    print(f"Reading PDF: {pdf_filename}")
    
    # Extract text from PDF
    try:
        reader = PdfReader(pdf_path)
        texts = []
        for page in reader.pages[:5]:  # Just first 5 pages for testing
            text = page.extract_text() or ""
            texts.append(text)
        full_text = "\n\n".join(texts)
        print(f"Extracted {len(full_text)} characters from PDF")
        
        # Print first 500 chars to see content
        print(f"\nFirst 500 chars of PDF:\n{full_text[:500]}")
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return
    
    # Simulate HR agent response (for debugging)
    sample_hr_response = '''
    [
        {
            "name": "Ева",
            "age": "25-30",
            "appearance": "стройная фигура, короткие тёмные волосы, яркие голубые глаза с пустым взглядом",
            "clothing": "стильный чёрный костюм для похода в бар с откровенным вырезом",
            "voice": "спокойная, холодная, в момент паники истеричная",
            "role": "главная героиня",
            "kieai_description": "Eva, 25-30 years old, slim figure, short dark hair, bright blue eyes with empty gaze, wearing stylish black bar suit with revealing neckline, calm and cold voice"
        },
        {
            "name": "Гарри",
            "age": "35-45",
            "appearance": "крупное телосложение, короткая седая щетина, пристальные карие глаза",
            "clothing": "практичная куртка для выезда на задание, прочные штаны",
            "voice": "твёрдый, уверенный, рассудительный",
            "role": "главный герой наставник",
            "kieai_description": "Harry, 35-45 years old, large build, short gray stubble, intense brown eyes, wearing practical mission jacket and durable pants, firm and confident voice"
        }
    ]
    '''
    
    print(f"\nSample HR response:\n{sample_hr_response}")
    
    # Extract JSON
    characters_data = _extract_json_array(sample_hr_response)
    print(f"\nExtracted {len(characters_data)} characters")
    
    for i, char in enumerate(characters_data):
        print(f"\nCharacter {i+1}:")
        for key, value in char.items():
            if key != 'kieai_description':
                print(f"  {key}: {repr(value)}")
                print(f"    Type: {type(value)}, Length: {len(str(value))}")
                # Check if value is bytes or string
                if isinstance(value, bytes):
                    print(f"    Is bytes! Decoding: {value.decode('utf-8', errors='replace')}")
    
    # Test database saving directly
    print(f"\n\nTesting direct database save...")
    import sqlite3
    conn = sqlite3.connect('memory/studio.db')
    
    for char_data in characters_data:
        name = char_data.get("name", "")
        print(f"\nSaving character: {repr(name)}")
        
        # Insert directly
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO characters (project_id, name, description, voice_id, relations, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                1,
                name,
                f"Возраст: {char_data.get('age', '')}. Внешность: {char_data.get('appearance', '')}. Одежда: {char_data.get('clothing', '')}. Голос: {char_data.get('voice', '')}",
                char_data.get("voice", ""),
                char_data.get("role", ""),
                "2026-04-05T22:37:49.462072"
            ))
            print(f"  Saved successfully!")
        except Exception as e:
            print(f"  Error: {e}")
    
    conn.commit()
    
    # Check what was saved
    print(f"\n\nChecking saved characters...")
    cursor.execute('SELECT id, name, description FROM characters')
    rows = cursor.fetchall()
    for row in rows:
        print(f"ID: {row[0]}, Name: {repr(row[1])}, Desc: {row[2][:50]}...")
        print(f"  Name hex: {row[1].encode('utf-8').hex() if row[1] else 'EMPTY'}")
    
    conn.close()

if __name__ == "__main__":
    asyncio.run(debug_hr_json())