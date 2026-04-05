import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
conn = sqlite3.connect('memory/studio.db')
cur = conn.cursor()
cur.execute("SELECT agent_id, name, role FROM agents WHERE agent_id='orchestrator'")
row = cur.fetchone()
print('DB row:', row)
conn.close()
