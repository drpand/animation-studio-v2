import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# Read correct instructions
with open('agents/instructions.json', 'r', encoding='utf-8') as f:
    instr = json.load(f)

# Agent definitions with correct roles
agents = [
    ('orchestrator', 'Orchestrator', 'Дирижёр — управляет всеми агентами, строит цепочки задач', 'deepseek/deepseek-v3.2'),
    ('director', 'Director', 'Режиссёр — принимает творческие решения по проекту', 'deepseek/deepseek-v3.2'),
    ('writer', 'Writer', 'Сценарист — адаптирует сцены сценария в промпты', 'deepseek/deepseek-v3.2'),
    ('critic', 'Critic', 'Критик — оценивает результат, даёт обратную связь', 'deepseek/deepseek-v3.2'),
    ('fixer', 'Fixer', 'Фиксер — исправляет по замечаниям Критика', 'deepseek/deepseek-v3.2'),
    ('storyboarder', 'Storyboarder', 'Раскадровщик — разбивает сцену на кадры с таймингом', 'deepseek/deepseek-v3.2'),
    ('dop', 'DOP', 'Оператор-постановщик — свет, угол камеры, атмосфера кадра', 'deepseek/deepseek-v3.2'),
    ('art_director', 'Art Director', 'Арт-директор — промпты для изображений, стиль, цвет', 'deepseek/deepseek-v3.2'),
    ('sound_director', 'Sound Director', 'Звуковой директор — музыка, голоса, звуковые эффекты', 'deepseek/deepseek-v3.2'),
    ('hr_agent', 'HR Agent', 'HR — создаёт нового агента под задачу если никто не справляется', 'deepseek/deepseek-v3.2'),
]

conn = sqlite3.connect('memory/studio.db')
cur = conn.cursor()

# Delete existing corrupted data
cur.execute('DELETE FROM agents')
cur.execute('DELETE FROM agent_attachments')
cur.execute('DELETE FROM agent_rules')
cur.execute('DELETE FROM messages')
conn.commit()

# Insert correct data
for agent_id, name, role, model in agents:
    instructions = instr.get(agent_id, '')
    cur.execute(
        'INSERT INTO agents (agent_id, name, role, model, status, instructions, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)',
        (agent_id, name, role, model, 'idle', instructions, '', '')
    )

conn.commit()

# Verify
cur.execute('SELECT agent_id, name, role FROM agents')
rows = cur.fetchall()
for r in rows:
    print(f'{r[0]:15} {r[1]:15} {r[2][:60]}')

conn.close()
print('\n[OK] Agents recreated successfully!')
