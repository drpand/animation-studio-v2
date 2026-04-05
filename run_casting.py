import os
import glob
import httpx
import json

print("--- STEP 2: CASTING ---")

# 1. Find the PDF file
files = glob.glob("memory/scripts/*Родина*.pdf")
if not files:
    print("ERROR: PDF file not found in memory/scripts/")
    exit(1)

pdf_filename = os.path.basename(files[0])
print(f"Found file: {pdf_filename}")

# 2. Call the API
url = "http://localhost:7860/api/orchestrator/full-casting"
payload = {"pdf_file": pdf_filename}

print(f"Calling {url}...")
try:
    response = httpx.post(url, json=payload, timeout=180)
    print(f"Status Code: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    # Extract names if present
    if "characters" in data:
        names = [c.get("name") for c in data["characters"]]
        print(f"\nExtracted Names: {names}")
    elif "detail" in data:
        print(f"Error Detail: {data['detail']}")
        
except Exception as e:
    print(f"Request failed: {e}")
