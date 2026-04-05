#!/usr/bin/env python3
"""
Test full casting directly
"""

import os
import sys
import asyncio
from pypdf import PdfReader

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from orchestrator.executor import run_full_casting
from database import async_session

async def test_direct():
    """Test full casting directly"""
    
    # Get PDF file
    scripts_dir = os.path.join(project_root, "memory", "scripts")
    try:
        pdf_files = [f for f in os.listdir(scripts_dir) if f.endswith('.pdf') and 'Родина' in f]
    except:
        print("Cannot access scripts directory")
        return
        
    if not pdf_files:
        print("No PDF file found")
        return
        
    pdf_file = pdf_files[0]
    pdf_path = os.path.join(scripts_dir, pdf_file)
    
    print(f"Reading PDF: {pdf_file}")
    
    # Read PDF
    try:
        reader = PdfReader(pdf_path)
        texts = []
        for page in reader.pages[:10]:  # First 10 pages
            text = page.extract_text() or ""
            texts.append(text)
        full_text = "\n\n".join(texts)
        print(f"Extracted {len(full_text)} characters")
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return
    
    # Run full casting
    print("Running full casting...")
    async with async_session() as db:
        result = await run_full_casting(full_text, db)
        print(f"Full casting returned {len(result)} characters")
        
        # Check database
        import crud
        characters = await crud.get_characters(db, 1)
        print(f"Database has {len(characters)} characters:")
        
        for char in characters:
            print(f"  ID: {char.id}, Name: '{char.name}', Desc: {char.description[:50]}...")

if __name__ == "__main__":
    asyncio.run(test_direct())