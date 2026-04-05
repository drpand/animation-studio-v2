#!/usr/bin/env python3
"""
Test what HR agent returns
"""

import os
import sys
import asyncio
import json
from pypdf import PdfReader

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator.executor import _extract_json_array, _run_agent_step

async def test_hr_agent():
    """Test HR agent directly"""
    
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
        for page in reader.pages[:50]:  # Max 50 pages
            text = page.extract_text() or ""
            texts.append(text)
        full_text = "\n\n".join(texts)
        print(f"Extracted {len(full_text)} characters from PDF")
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return
    
    # HR prompt
    hr_prompt = (
        "Извлеки ВСЕХ персонажей из текста сценария. ВАЖНО: создавай карточки ТОЛЬКО для персонажей "
        "которые реально появляются в тексте. НЕ выдумывай персонажей.\n\n"
        "Верни СТРОГО JSON массив, НИЧЕГО кроме JSON:\n"
        "[{\"name\":\"Имя\",\"age\":\"возраст\",\"appearance\":\"внешность\","
        "\"clothing\":\"одежда\",\"voice\":\"манера речи\",\"role\":\"роль\","
        "\"kieai_description\":\"English description for AI image generation\"}]\n\n"
        f"Текст сценария:\n{full_text[:15000]}"
    )
    
    print("\nSending to HR agent...")
    hr_result, hr_success = await _run_agent_step("hr_agent", hr_prompt, "test_task")
    
    if not hr_success:
        print(f"HR failed: {hr_result}")
        return
    
    print(f"\nHR result (first 1000 chars):\n{hr_result[:1000]}")
    
    # Extract JSON
    characters_data = _extract_json_array(hr_result)
    print(f"\nExtracted {len(characters_data)} characters")
    
    for i, char in enumerate(characters_data):
        print(f"\nCharacter {i+1}:")
        for key, value in char.items():
            if key != 'kieai_description':
                print(f"  {key}: {repr(value)}")
    
    # Test saving
    print(f"\nTesting name extraction:")
    for char_data in characters_data:
        name = char_data.get("name", "")
        print(f"  Name: {repr(name)}")
        print(f"  Name type: {type(name)}")
        print(f"  Name length: {len(name)}")

if __name__ == "__main__":
    asyncio.run(test_hr_agent())