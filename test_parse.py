import re

task_desc = """Аниме 2.5D реализм. Панда-самурай точит свой меч в храме. 
Философия + триллер. Формат 16:9. Длительность 80 секунд.
4 кадра."""

# Парсим количество кадров
frames_match = re.search(r'(\d+)\s*кадр[аов]?', task_desc, re.IGNORECASE)
num_frames = int(frames_match.group(1)) if frames_match else 1

print(f"Найдено кадров: {num_frames}")
print(f"Match: {frames_match}")
if frames_match:
    print(f"Group 1: {frames_match.group(1)}")
