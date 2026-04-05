"""
Миграция: добавить поле access_level в таблицу agents.
"""
import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'memory/studio.db'

# Маппинг agent_id -> access_level
ACCESS_LEVELS = {
    'orchestrator': 'level_3',       # наблюдение
    'critic': 'level_2',             # производство — оценка
    'fixer': 'level_2',              # производство — исправление
    'writer': 'production',          # производство
    'director': 'production',        # производство
    'dop': 'production',             # производство
    'art_director': 'production',    # производство
    'sound_director': 'production',  # производство
    'storyboarder': 'production',    # производство
    'hr_agent': 'production',        # производство
}

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Проверяем существует ли колонка
cur.execute("PRAGMA table_info(agents)")
columns = [row[1] for row in cur.fetchall()]

if 'access_level' not in columns:
    print("Добавляю колонку access_level...")
    cur.execute("ALTER TABLE agents ADD COLUMN access_level TEXT DEFAULT 'production'")
    
    # Заполняем значения
    for agent_id, level in ACCESS_LEVELS.items():
        cur.execute("UPDATE agents SET access_level = ? WHERE agent_id = ?", (level, agent_id))
        print(f"  {agent_id} -> {level}")
    
    conn.commit()
    print("✅ Миграция завершена")
else:
    print("Колонка access_level уже существует")

# Проверяем результат
cur.execute("SELECT agent_id, name, access_level FROM agents")
rows = cur.fetchall()
print("\nТекущие агенты:")
for r in rows:
    print(f"  {r[0]:20} {r[1]:20} {r[2]}")

conn.close()
