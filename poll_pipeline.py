import requests, json, time

start = time.time()
max_wait = 300  # 5 min

while time.time() - start < max_wait:
    r = requests.get('http://localhost:7860/api/orchestrator/scene-result/1/1/1')
    data = r.json()
    status = data.get('status', 'unknown')
    
    if status != 'not_found':
        elapsed = int(time.time() - start)
        print(f'[{elapsed}s] STATUS: {status}')
        wt = data.get('writer_text', '') or ''
        dn = data.get('director_notes', '') or ''
        cj = data.get('characters_json', '') or ''
        dp = data.get('dop_prompt', '') or ''
        ap = data.get('art_prompt', '') or ''
        sp = data.get('sound_prompt', '') or ''
        fp = data.get('final_prompt', '') or ''
        iu = data.get('image_url', '') or ''
        cf = data.get('critic_feedback', '') or ''
        us = data.get('user_status', 'pending')
        
        print(f'  writer_text: {len(wt)} chars')
        print(f'  director_notes: {len(dn)} chars')
        print(f'  characters_json: {len(cj)} chars')
        print(f'  dop_prompt: {len(dp)} chars')
        print(f'  art_prompt: {len(ap)} chars')
        print(f'  sound_prompt: {len(sp)} chars')
        print(f'  final_prompt: {len(fp)} chars')
        print(f'  image_url: {"SET" if iu else "EMPTY"}')
        print(f'  critic_feedback: {len(cf)} chars')
        print(f'  user_status: {us}')
        
        if status in ('approved', 'in_review'):
            print('\n=== PIPELINE COMPLETE ===')
            print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
            break
    
    # Check agents status
    agents_r = requests.get('http://localhost:7860/api/agents/')
    agents = agents_r.json().get('agents', [])
    working = [a['agent_id'] for a in agents if a.get('status') == 'working']
    if working:
        elapsed = int(time.time() - start)
        print(f'[{elapsed}s] Working agents: {working}')
    
    time.sleep(10)
else:
    print('TIMEOUT after 5 minutes')
