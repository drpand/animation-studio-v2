import sqlite3
conn = sqlite3.connect('memory/studio.db')
cur = conn.cursor()
cur.execute("SELECT agent_id, filename, original_name, is_text_readable, size_bytes FROM agent_attachments WHERE original_name LIKE '%Rodina%' OR original_name LIKE '%Родина%' ORDER BY uploaded_at DESC LIMIT 5")
rows = cur.fetchall()
for r in rows:
    print(f'Agent: {r[0]}, File: {r[1]}, Original: {r[2]}, Readable: {r[3]}, Size: {r[4]} bytes')
conn.close()
