import sqlite3
import sys

conn = sqlite3.connect('memory/studio.db')
rows = conn.execute('SELECT id, name FROM characters').fetchall()

print("ID, Name (repr), Name (raw), Name (hex)")
print("-" * 80)

for r in rows:
    name = r[1]
    name_repr = repr(name)
    name_hex = name.encode('utf-8').hex() if name else ''
    
    print(f"{r[0]}, {name_repr}, '{name}', {name_hex}")

conn.close()