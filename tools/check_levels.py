import urllib.request, json
r = urllib.request.urlopen('http://localhost:7860/api/agents/')
data = json.loads(r.read())
for a in data['agents']:
    print(f'{a["agent_id"]:20} level={a.get("access_level","?")}')
