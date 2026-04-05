import sqlite3
conn = sqlite3.connect('memory/studio.db')
cur = conn.cursor()
cur.execute("SELECT role, substr(content, 1, 500) FROM messages WHERE agent_id='writer' ORDER BY time DESC LIMIT 2")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f'Role: {row[0]}')
        print(f'Content: {row[1][:300]}...')
        print('---')
else:
    print('No messages for writer yet')
conn.close()
