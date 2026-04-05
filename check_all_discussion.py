import json
with open('memory/discussion_log.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
msgs = data.get('messages', [])
print(f'Total messages: {len(msgs)}')
print('\n=== ALL MESSAGES ===')
for m in msgs:
    content = m.get('content', '')[:150]
    ts = m.get('timestamp', '')[:19]
    aid = m.get('agent_id', '')
    mtype = m.get('msg_type', '')
    print(f'[{ts}] {aid:20s} {mtype:8s} {content}')
