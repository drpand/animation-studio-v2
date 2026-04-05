#!/usr/bin/env python3
# Check API endpoints

import os
import re

api_file = 'api/orchestrator_api.py'
if os.path.exists(api_file):
    with open(api_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check for full-casting endpoint
    if '@router.post("/full-casting")' in content:
        print('✅ Full-casting endpoint exists in orchestrator_api.py')
    else:
        print('❌ Full-casting endpoint NOT found')
        
    # Search for all endpoints
    print('\nSearching for endpoints in orchestrator_api.py:')
    matches = re.findall(r'@router\.(?:post|get|put|delete)\(\"([^\"]+)\"\)', content)
    for match in matches:
        print(f'  - {match}')
else:
    print(f'❌ API file not found: {api_file}')

# Also check main.py for mounted routes
print('\nChecking main.py for mounted routes:')
main_file = 'main.py'
if os.path.exists(main_file):
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'orchestrator_api' in content:
            print('✅ orchestrator_api is mounted')
        if '/api/orchestrator' in content:
            print('✅ /api/orchestrator prefix found')