#!/usr/bin/env python3
"""
Test script for full casting functionality
"""

import os
import sys
import asyncio
from pypdf import PdfReader

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator.executor import run_full_casting
from database import async_session

async def test_full_casting():
    """Test the full casting functionality"""
    
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
    
    # Run full casting
    print("Running full casting...")
    async with async_session() as db:
        characters = await run_full_casting(full_text, db)
        
    print(f"Found {len(characters)} characters:")
    for char in characters:
        print(f"  - {char.get('name', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(test_full_casting())