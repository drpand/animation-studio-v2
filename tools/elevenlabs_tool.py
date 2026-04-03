"""
ElevenLabs Tool — генерация голоса через ElevenLabs API.
"""
import os
import uuid
import time
import asyncio
import httpx
from pathlib import Path

from config import ELEVENLABS_API_KEY, ELEVENLABS_RETRY_ATTEMPTS, ELEVENLABS_RETRY_BASE_DELAY, MAX_PROMPT_LENGTH
from tools.base_tool import ToolResponse

AUDIO_CACHE_DIR = Path(__file__).parent.parent / "memory" / "tools_cache" / "audio"
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def list_voices() -> list[dict]:
    """Получить список доступных голосов."""
    if not ELEVENLABS_API_KEY:
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
            voices = data.get("voices", [])
            return [
                {
                    "voice_id": v.get("voice_id", ""),
                    "name": v.get("name", ""),
                    "category": v.get("category", ""),
                }
                for v in voices
            ]
    except Exception:
        return []


async def generate_audio(text: str, voice_id: str, model: str = "eleven_multilingual_v2") -> ToolResponse:
    """
    Генерация аудио через ElevenLabs с retry и exponential backoff.
    """
    start = time.time()

    text = text.strip()
    if not text:
        return ToolResponse(status="error", error="Пустой текст", elapsed_ms=0)
    if len(text) > MAX_PROMPT_LENGTH:
        return ToolResponse(
            status="error",
            error=f"Текст слишком длинный: {len(text)} символов. Максимум: {MAX_PROMPT_LENGTH}",
            elapsed_ms=0,
        )
    if not voice_id:
        return ToolResponse(status="error", error="Не выбран голос", elapsed_ms=0)
    if not ELEVENLABS_API_KEY:
        return ToolResponse(
            status="error",
            error="API ключ ElevenLabs не настроен. Добавьте ELEVENLABS_API_KEY в .env",
            elapsed_ms=0,
        )

    for attempt in range(ELEVENLABS_RETRY_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": ELEVENLABS_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": model,
                        "output_format": "mp3_44100_128",
                    },
                )
                resp.raise_for_status()

                # Сохраняем аудио
                filename = f"{uuid.uuid4().hex[:12]}.mp3"
                dest = AUDIO_CACHE_DIR / filename
                dest.write_bytes(resp.content)

                elapsed = int((time.time() - start) * 1000)
                return ToolResponse(
                    status="success",
                    result_url=f"/static/tools_cache/audio/{filename}",
                    elapsed_ms=elapsed,
                    metadata={"voice_id": voice_id, "model": model},
                )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return ToolResponse(
                    status="error",
                    error="Неверный API ключ ElevenLabs. Проверьте .env",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
            if e.response.status_code == 429 and attempt < ELEVENLABS_RETRY_ATTEMPTS - 1:
                delay = ELEVENLABS_RETRY_BASE_DELAY ** (attempt + 1)
                await asyncio.sleep(delay)
                continue
            return ToolResponse(
                status="error",
                error=f"ElevenLabs ошибка: {e.response.status_code}",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < ELEVENLABS_RETRY_ATTEMPTS - 1:
                delay = ELEVENLABS_RETRY_BASE_DELAY ** (attempt + 1)
                await asyncio.sleep(delay)
            else:
                return ToolResponse(
                    status="error",
                    error=f"Сетевая ошибка: {str(e)} (исчерпаны {ELEVENLABS_RETRY_ATTEMPTS} попытки)",
                    elapsed_ms=int((time.time() - start) * 1000),
                )

    return ToolResponse(
        status="error",
        error="Все попытки генерации неудачны",
        elapsed_ms=int((time.time() - start) * 1000),
    )
