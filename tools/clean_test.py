import sqlite3
conn = sqlite3.connect('memory/studio.db')
cur = conn.cursor()
cur.execute("DELETE FROM agent_attachments WHERE filename LIKE '%test_script%'")
conn.commit()
print('Deleted test_script attachments')
conn.close()
