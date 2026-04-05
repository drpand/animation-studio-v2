#!/usr/bin/env python3
"""
Run full casting through API endpoint
"""

import httpx
import json
import sys
import os

# Get PDF file from scripts directory
project_root = os.path.dirname(os.path.abspath(__file__))
scripts_dir = os.path.join(project_root, "memory", "scripts")

# Find PDF file
pdf_files = [f for f in os.listdir(scripts_dir) if f.endswith('.pdf') and 'Родина' in f]
if not pdf_files:
    print("No PDF file found")
    sys.exit(1)

pdf_file = pdf_files[0]
print(f"Using PDF file: {pdf_file}")

# Make API call to full-casting endpoint
url = "http://localhost:7860/api/orchestrator/full-casting"
payload = {
    "pdf_file": pdf_file
}

try:
    print(f"Calling {url}...")
    response = httpx.post(url, json=payload, timeout=300)
    result = response.json()
    print(f"Response status: {response.status_code}")
    print(f"Response: {json.dumps(result, ensure_ascii=False, indent=2)}")
except Exception as e:
    print(f"Error: {e}")
    
# Wait a moment and check database
print("\n\nChecking database after full casting...")
import sqlite3
conn = sqlite3.connect('memory/studio.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, description FROM characters')
rows = cursor.fetchall()

print(f"Found {len(rows)} characters in database:")
for row in rows:
    print(f"ID: {row[0]}, Name: '{row[1]}', Desc preview: {row[2][:50]}...")

conn.close()