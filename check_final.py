import httpx, json

r = httpx.get('http://localhost:7860/api/orchestrator/scene-result/1/1/1', timeout=10)
d = r.json()
print('=== SCENE 1 FINAL ===')
print('status:', d.get('status'))
print('user_status:', d.get('user_status'))
print('image_url:', d.get('image_url'))
print('final_prompt:', d.get('final_prompt', '')[:200])
print()

r2 = httpx.get('http://localhost:7860/api/characters/', timeout=10)
data = r2.json()
chars = data.get('characters', [])
print(f'=== CHARACTERS ({len(chars)}) ===')
for c in chars:
    cid = c.get('id', 0)
    cname = c.get('name', '')
    cdesc = c.get('description', '')[:100]
    print(f'  ID={cid:3d}  name={cname}  desc={cdesc}')
