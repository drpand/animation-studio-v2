import json
with open('memory/discussion_log.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
msgs = data.get('messages', [])[-20:]
for m in msgs:
    content = m.get('content', '')[:120]
    ts = m.get('timestamp', '')[:19]
    aid = m.get('agent_id', '')
    mtype = m.get('msg_type', '')
    print(f'[{ts}] {aid:15s} {mtype:8s} {content}')
