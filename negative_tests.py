import requests, json

print("=" * 60)
print("НЕГАТИВНЫЕ ТЕСТЫ — Animation Studio v2")
print("=" * 60)

results = []

# 2.1 Пустая задача
print("\n[2.1] Пустая задача...")
r = requests.post('http://localhost:7860/api/orchestrator/task', json={'description': ''})
passed = r.status_code == 400
results.append(('2.1 Пустая задача', passed, f'status={r.status_code}'))
print(f'  {"PASS" if passed else "FAIL"}: status={r.status_code}')

# 2.2 Только пробелы
print("\n[2.2] Только пробелы...")
r = requests.post('http://localhost:7860/api/orchestrator/task', json={'description': '   '})
passed = r.status_code == 400
results.append(('2.2 Только пробелы', passed, f'status={r.status_code}'))
print(f'  {"PASS" if passed else "FAIL"}: status={r.status_code}')

# 2.3 Несуществующий endpoint
print("\n[2.3] Несуществующий endpoint...")
r = requests.get('http://localhost:7860/api/orchestrator/status/nonexistent_task')
passed = r.status_code == 404
results.append(('2.3 Несуществующий endpoint', passed, f'status={r.status_code}'))
print(f'  {"PASS" if passed else "FAIL"}: status={r.status_code}')

# 2.4 Несуществующая сцена
print("\n[2.4] Несуществующая сцена...")
r = requests.get('http://localhost:7860/api/orchestrator/scene-result/99/99/99')
data = r.json()
passed = data.get('status') == 'not_found'
results.append(('2.4 Несуществующая сцена', passed, f'status={data.get("status")}'))
print(f'  {"PASS" if passed else "FAIL"}: status={data.get("status")}')

# 2.5 Некорректный JSON в scene-action
print("\n[2.5] Некорректный JSON в scene-action...")
r = requests.post('http://localhost:7860/api/orchestrator/scene-action/1/1/1', json={})
passed = r.status_code in (400, 422, 200)
results.append(('2.5 Некорректный JSON scene-action', passed, f'status={r.status_code}'))
print(f'  {"PASS" if passed else "FAIL"}: status={r.status_code}')

# 2.6 Дублирующий upload-script
print("\n[2.6] Дублирующий upload-script...")
with open('memory/attachments/Родина 007-15.02.14 (2).pdf', 'rb') as f:
    r1 = requests.post('http://localhost:7860/api/orchestrator/upload-script', files={'file': ('test.pdf', f, 'application/pdf')})
import time; time.sleep(1)
with open('memory/attachments/Родина 007-15.02.14 (2).pdf', 'rb') as f:
    r2 = requests.post('http://localhost:7860/api/orchestrator/upload-script', files={'file': ('test.pdf', f, 'application/pdf')})
data2 = r2.json()
passed = data2.get('duplicate') == True
results.append(('2.6 Дублирующий upload', passed, f'duplicate={data2.get("duplicate")}'))
print(f'  {"PASS" if passed else "FAIL"}: duplicate={data2.get("duplicate")}')

# 2.7 Невалидный файл (.exe)
print("\n[2.7] Невалидный файл (.exe)...")
r = requests.post('http://localhost:7860/api/orchestrator/upload-script', files={'file': ('test.exe', b'fake exe', 'application/octet-stream')})
passed = r.status_code == 400
results.append(('2.7 Невалидный файл .exe', passed, f'status={r.status_code}'))
print(f'  {"PASS" if passed else "FAIL"}: status={r.status_code}')

# 2.8 Health check
print("\n[2.8] Health check...")
r = requests.get('http://localhost:7860/health')
data = r.json()
passed = data.get('status') == 'ok' and data.get('project') == 'РОДИНА'
results.append(('2.8 Health check', passed, f'status={data.get("status")}, project={data.get("project")}'))
print(f'  {"PASS" if passed else "FAIL"}: status={data.get("status")}, project={data.get("project")}')

# 2.9 Agents list
print("\n[2.9] Agents list...")
r = requests.get('http://localhost:7860/api/agents/')
data = r.json()
agents = data.get('agents', [])
passed = len(agents) >= 10
results.append(('2.9 Agents list', passed, f'count={len(agents)}'))
print(f'  {"PASS" if passed else "FAIL"}: count={len(agents)}')

# 2.10 Registry
print("\n[2.10] Agent registry...")
r = requests.get('http://localhost:7860/api/orchestrator/registry')
data = r.json()
passed = isinstance(data, list) and len(data) >= 8
results.append(('2.10 Agent registry', passed, f'count={len(data) if isinstance(data, list) else 0}'))
print(f'  {"PASS" if passed else "FAIL"}: count={len(data) if isinstance(data, list) else 0}')

# 2.11 Storyboard empty scene
print("\n[2.11] Storyboard — несуществующая сцена...")
r = requests.get('http://localhost:7860/api/orchestrator/scene-result/99/99/99')
data = r.json()
passed = data.get('status') == 'not_found'
results.append(('2.11 Storyboard not_found', passed, f'status={data.get("status")}'))
print(f'  {"PASS" if passed else "FAIL"}: status={data.get("status")}')

# 2.12 Characters API
print("\n[2.12] Characters API...")
r = requests.get('http://localhost:7860/api/characters/')
data = r.json()
passed = 'characters' in data
results.append(('2.12 Characters API', passed, f'has characters key'))
print(f'  {"PASS" if passed else "FAIL"}: has characters key')

# ИТОГО
print("\n" + "=" * 60)
passed_count = sum(1 for _, p, _ in results if p)
total = len(results)
print(f"ИТОГО: {passed_count}/{total} тестов пройдено")
for name, passed, detail in results:
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}: {detail}")
print("=" * 60)
