import sqlite3
conn = sqlite3.connect('memory/studio.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, description FROM characters')
rows = cursor.fetchall()
print(f'Total characters in database: {len(rows)}')
for row in rows:
    print(f'ID: {row[0]}, Name: \"{row[1]}\"')
conn.close()