import requests, json, time

start = time.time()
max_wait = 300  # 5 min
last_status = ""

while time.time() - start < max_wait:
    r = requests.get('http://localhost:7860/api/orchestrator/scene-result/1/1/1')
    data = r.json()
    status = data.get('status', 'unknown')
    elapsed = int(time.time() - start)
    
    if status != last_status:
        print(f'[{elapsed}s] STATUS CHANGED: {status}')
        last_status = status
    
    if status != 'not_found':
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
        
        print(f'[{elapsed}s] writer={len(wt)} director={len(dn)} hr={len(cj)} dop={len(dp)} art={len(ap)} sound={len(sp)} final={len(fp)} image={"SET" if iu else "EMPTY"} user_status={us}')
        
        if status in ('approved', 'in_review'):
            print('\n=== PIPELINE COMPLETE ===')
            print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
            break
    
    # Check agents status
    agents_r = requests.get('http://localhost:7860/api/agents/')
    agents = agents_r.json().get('agents', [])
    working = [a['agent_id'] for a in agents if a.get('status') == 'working']
    if working:
        print(f'[{elapsed}s] Working: {working}')
    
    time.sleep(15)
else:
    print(f'\nTIMEOUT after {max_wait} seconds')
