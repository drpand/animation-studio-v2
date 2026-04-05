import httpx, json

r = httpx.get('http://localhost:7860/api/characters/', timeout=10)
data = r.json()
chars = data.get('characters', [])
print(f'Total characters: {len(chars)}')
print()
for c in chars:
    cid = c.get('id', 0)
    cname = c.get('name', '')
    cdesc = c.get('description', '')[:80]
    print(f'ID={cid:3d}  {cname:15s}  {cdesc}')
