"""
Prompt Builder — утилиты парсинга JSON, построения промптов и санитизации текста.
Вынесено из orchestrator/executor.py для улучшения поддерживаемости.
"""
import re
import json


def _extract_json(text: str) -> dict:
    """Извлечь JSON из ответа LLM (игнорируя маркдаун и лишний текст)."""
    if not text:
        return {}
    
    # Сначала ищем JSON внутри markdown-блока
    md_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return {}


def _extract_json_array(text: str) -> list:
    """Извлечь JSON массив из ответа LLM."""
    if not text:
        return []
    
    # Если текст начинается с кавычки, это может быть JSON-строка с экранированным массивом
    if text.strip().startswith('"'):
        try:
            text = json.loads(text)
        except json.JSONDecodeError:
            pass
    
    # Сначала ищем JSON внутри markdown-блока ```json ... ```
    md_match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    
    # Ищем JSON массив в тексте
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return []
    return []


def _extract_names_to_remove(feedback: str) -> list:
    """Извлечь имена персонажей для удаления из feedback Critic."""
    names = []
    for line in feedback.split('\n'):
        line = line.strip()
        if any(kw in line.lower() for kw in ['галлюцин', 'удал', 'нет в тексте', 'не упоминается', 'выдуман']):
            # Ищем имена в кавычках или после тире
            quoted = re.findall(r'["«"]([^"»"]+)["»"]', line)
            names.extend(quoted)
    return names


def _safe_text(value) -> str:
    """Безопасно привести значение к строке для логов/промптов."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _safe_text_list(values) -> list:
    """Нормализовать список значений в список строк (без пустых)."""
    if not isinstance(values, list):
        return []
    result = []
    for v in values:
        text = _safe_text(v).strip()
        if text:
            result.append(text)
    return result


def _sanitize_image_text(text: str) -> str:
    """Очистить текст от видео-таймингов и motion-терминов для статичного image prompt."""
    t = _safe_text(text)
    if not t:
        return ""

    # Таймкоды и явные длительности
    t = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b\d+\s*(секунд|сек|seconds?|s|fps)\b", " ", t, flags=re.IGNORECASE)

    # Термины движения камеры/монтажа (ru/en)
    motion_terms = [
        "dolly", "dolly in", "dolly out", "pan", "tilt", "zoom", "tracking", "truck",
        "crane", "orbit", "whip pan", "camera movement", "camera move", "transition",
        "cut to", "crossfade", "montage", "sequence", "shot-reverse-shot",
        "долли", "панорама", "панорамирование", "наклон камеры", "зум", "наезд", "отъезд",
        "треккинг", "кран", "орбита", "монтаж", "переход", "склейка", "последовательность",
        "кадр за кадром", "тайминг", "хронометраж"
    ]
    for term in motion_terms:
        t = re.sub(rf"\b{re.escape(term)}\b", " ", t, flags=re.IGNORECASE)

    # Нормализация пробелов/пунктуации
    t = re.sub(r"\s+", " ", t).strip(" ,.;:-")
    return t


def _pick_visual_phrase(parts: dict, keys: list, default: str = "") -> str:
    """Взять первое валидное визуальное поле из списка ключей."""
    for k in keys:
        v = parts.get(k)
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            continue
        s = _sanitize_image_text(str(v))
        if s:
            return s
    return default


def _build_strict_image_parts(parts: dict) -> dict:
    """Собрать структурные image-поля (карточка кадра) из решений цехов."""
    subject = _pick_visual_phrase(parts, ["character", "subject"], "adult human protagonist")
    location = _pick_visual_phrase(parts, ["location", "environment", "background"], "night exterior")
    lighting = _pick_visual_phrase(parts, ["lighting"], "cinematic low-key lighting")
    style = _pick_visual_phrase(parts, ["style"], "cinematic illustration, detailed textures")
    palette = _pick_visual_phrase(parts, ["palette", "color_palette"], "cold muted contrast")
    # Mood может приходить от sound_director (не подходит для image prompt),
    # поэтому читаем только визуальную атмосферу.
    mood = _pick_visual_phrase(parts, ["atmosphere", "visual_mood"], "tense dramatic mood")
    composition = _pick_visual_phrase(parts, ["shot", "composition", "framing"], "single static composition")
    return {
        "subject": subject,
        "location": location,
        "lighting": lighting,
        "style": style,
        "palette": palette,
        "mood": mood,
        "composition": composition,
        "constraints": [
            "aspect ratio 16:9",
            "single still frame",
            "no camera movement",
            "no transitions",
            "no sequence",
            "no storyboard panels",
            "no subtitles",
            "no text",
            "no watermark",
        ],
    }


def _compose_image_prompt(parts: dict) -> str:
    """Собрать строковый image prompt из структурных полей карточки кадра."""
    strict_parts = [
        f"subject: {_safe_text(parts.get('subject', 'adult human protagonist'))}",
        f"location: {_safe_text(parts.get('location', 'night exterior'))}",
        f"lighting: {_safe_text(parts.get('lighting', 'cinematic low-key lighting'))}",
        f"style: {_safe_text(parts.get('style', 'cinematic illustration, detailed textures'))}",
        f"palette: {_safe_text(parts.get('palette', 'cold muted contrast'))}",
        f"mood: {_safe_text(parts.get('mood', 'tense dramatic mood'))}",
        f"composition: {_safe_text(parts.get('composition', 'single static composition'))}",
    ]
    constraints = parts.get("constraints", [])
    if isinstance(constraints, list):
        strict_parts.extend([_safe_text(c) for c in constraints if _safe_text(c)])
    prompt = ", ".join([p for p in strict_parts if p])
    return prompt[:800]


def _build_strict_image_prompt(parts: dict) -> str:
    """Backward-compatible wrapper: принимает сырые части, возвращает image-only prompt."""
    return _compose_image_prompt(_build_strict_image_parts(parts))


def _contains_panda(text: str) -> bool:
    t = _safe_text(text).lower()
    return ("panda" in t) or ("панда" in t)


def _sanitize_subject_leakage(subject: str, context: dict) -> str:
    """Очистка subject от утечек сущностей, которых нет в текущей сцене."""
    s = _safe_text(subject)
    writer_text = _safe_text(context.get("writer_text", ""))
    task_text = _safe_text(context.get("task_text", ""))
    hr_text = _safe_text(context.get("hr_text", ""))
    full_context = f"{writer_text}\n{task_text}\n{hr_text}".lower()
    panda_allowed = ("panda" in full_context) or ("панда" in full_context)
    if not panda_allowed and _contains_panda(s):
        s = re.sub(r"\bsamurai panda\b", "adult human protagonist", s, flags=re.IGNORECASE)
        s = re.sub(r"\bpanda samurai\b", "adult human protagonist", s, flags=re.IGNORECASE)
        s = re.sub(r"\bpanda\b", "adult human", s, flags=re.IGNORECASE)
        s = re.sub(r"панда[-\s]?самурай", "взрослый человек", s, flags=re.IGNORECASE)
        s = re.sub(r"панда", "взрослый человек", s, flags=re.IGNORECASE)
    return s[:300]


def _sanitize_entity_leakage(prompt: str, context: dict) -> str:
    """Убирает утечку сущностей (например, panda), если их нет в текущем контексте задачи."""
    p = _safe_text(prompt)
    # Контекст текущей сцены
    writer_text = _safe_text(context.get("writer_text", ""))
    task_text = _safe_text(context.get("task_text", ""))
    hr_text = _safe_text(context.get("hr_text", ""))
    full_context = f"{writer_text}\n{task_text}\n{hr_text}".lower()

    panda_allowed = ("panda" in full_context) or ("панда" in full_context)
    if not panda_allowed and _contains_panda(p):
        # Жёстко заменяем panda-сущности на нейтрального персонажа
        p = re.sub(r"\bsamurai panda\b", "adult human protagonist", p, flags=re.IGNORECASE)
        p = re.sub(r"\bpanda samurai\b", "adult human protagonist", p, flags=re.IGNORECASE)
        p = re.sub(r"\bpanda\b", "adult human", p, flags=re.IGNORECASE)
        p = re.sub(r"панда[-\s]?самурай", "взрослый человек", p, flags=re.IGNORECASE)
        p = re.sub(r"панда", "взрослый человек", p, flags=re.IGNORECASE)

    return p[:800]


def _build_kieai_prompt(parts: dict) -> str:
    """Собрать финальный промпт из JSON частей цехов для Z-Image Turbo.
    Kie.ai Z-Image имеет лимит ~800 символов — собираем компактно."""
    # Жёсткая image-only сборка: только визуальные поля и строгие ограничения.
    return _build_strict_image_prompt(parts)
