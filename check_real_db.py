import sqlite3, json
conn = sqlite3.connect('memory/studio.db')
conn.row_factory = sqlite3.Row

# Check tables
print("Tables in database:")
c = conn.cursor()
c.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = c.fetchall()
for table in tables:
    print(f"  - {table[0]}")

# Check characters table
print("\nCharacters table data:")
try:
    rows = conn.execute('SELECT id, name, description, voice_id, relations, created_at FROM characters').fetchall()
    for r in rows:
        print(dict(r))
except Exception as e:
    print(f"Error: {e}")

conn.close()