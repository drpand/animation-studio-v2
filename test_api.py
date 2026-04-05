#!/usr/bin/env python3
# Simple API check

import os
import re

api_file = 'api/orchestrator_api.py'
if os.path.exists(api_file):
    with open(api_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check for full-casting endpoint
    if '@router.post("/full-casting")' in content:
        print('Full-casting endpoint exists')
    else:
        print('Full-casting endpoint NOT found')
        
    # Search for endpoints
    print('\nEndpoints in orchestrator_api.py:')
    matches = re.findall(r'@router\.(?:post|get|put|delete)\(\"([^\"]+)\"\)', content)
    for match in matches:
        print(f'  {match}')

# Test actual API call
print('\nTesting actual API call...')
import httpx
try:
    # Try with correct path
    r = httpx.post('http://localhost:7860/api/orchestrator/full-casting',
        json={'pdf_file': 'test.pdf'}, timeout=10)
    print(f'Status: {r.status_code}')
    print(f'Response: {r.json()}')
except Exception as e:
    print(f'Error: {e}')