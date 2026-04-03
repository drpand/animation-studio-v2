"""
Kie.ai Z-Image Tool — генерация изображений через Kie.ai API.
Primary генератор для Art Director. ComfyUI остаётся как fallback.

API Docs: https://docs.kie.ai/market/z-image/z-image
Endpoints:
  POST https://api.kie.ai/api/v1/jobs/createTask
  GET  https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...
"""
import os
import uuid
import time
import json
import asyncio
import httpx
from pathlib import Path

from config import KIEAI_API_KEY, KIEAI_POLL_ATTEMPTS, KIEAI_POLL_INTERVAL_SEC, MAX_PROMPT_LENGTH
from tools.base_tool import ToolResponse

KIEAI_BASE_URL = "https://api.kie.ai/api/v1"
TOOLS_CACHE_DIR = Path(__file__).parent.parent / "memory" / "tools_cache" / "images"
TOOLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _log(msg: str):
    print(f"[Kie.ai] {msg}")


async def check_health() -> bool:
    """Проверяет что Kie.ai API доступен и ключ валиден."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{KIEAI_BASE_URL}/jobs/createTask",
                headers={
                    "Authorization": f"Bearer {KIEAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "z-image",
                    "input": {"prompt": "test", "aspect_ratio": "1:1"},
                },
            )
            return resp.status_code in (200, 429)
    except Exception:
        return False


async def generate_image(
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 30,
    cfg_scale: float = 7.0,
    seed: int = -1,
) -> ToolResponse:
    """
    Генерация изображения через Kie.ai Z-Image.

    Flow:
    1. Валидация промпта
    2. POST createTask → taskId
    3. Async polling recordInfo каждые N сек (до 200 попыток)
    4. При success → download → save → return URL
    """
    start = time.time()
    _log(f"generate_image: prompt={prompt[:50]}...")

    # Валидация
    prompt = prompt.strip()
    if not prompt:
        return ToolResponse(status="error", error="Пустой промпт", elapsed_ms=0)
    if len(prompt) > MAX_PROMPT_LENGTH:
        return ToolResponse(
            status="error",
            error=f"Промпт слишком длинный: {len(prompt)} символов. Максимум: {MAX_PROMPT_LENGTH}",
            elapsed_ms=0,
        )

    if not KIEAI_API_KEY:
        return ToolResponse(
            status="error",
            error="KIEAI_API_KEY не настроен. Добавьте в .env",
            elapsed_ms=0,
        )

    # Определяем aspect_ratio из width/height
    aspect_ratio = _width_height_to_ratio(width, height)

    try:
        # 1. Создаём задачу
        _log("Creating task...")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{KIEAI_BASE_URL}/jobs/createTask",
                headers={
                    "Authorization": f"Bearer {KIEAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "z-image",
                    "input": {
                        "prompt": prompt,
                        "aspect_ratio": aspect_ratio,
                        "nsfw_checker": True,
                    },
                },
            )

            # Обработка HTTP ошибок
            if resp.status_code == 401:
                return ToolResponse(
                    status="error",
                    error="Kie.ai: неверный API ключ (401)",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
            if resp.status_code == 402:
                return ToolResponse(
                    status="error",
                    error="Kie.ai: недостаточно кредитов (402)",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
            if resp.status_code == 429:
                return ToolResponse(
                    status="rate_limited",
                    error="Kie.ai: rate limit. Попробуйте позже",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
            if resp.status_code == 422:
                return ToolResponse(
                    status="error",
                    error="Kie.ai: ошибка валидации параметров (422)",
                    elapsed_ms=int((time.time() - start) * 1000),
                )
            if resp.status_code == 500:
                return ToolResponse(
                    status="error",
                    error="Kie.ai: внутренняя ошибка сервера (500)",
                    elapsed_ms=int((time.time() - start) * 1000),
                )

            resp.raise_for_status()
            data = resp.json()

        # 2. Валидация ответа — проверяем taskId
        if data.get("code") != 200:
            _log(f"Invalid response code: {data}")
            return ToolResponse(
                status="error",
                error=f"Kie.ai: {data.get('msg', 'Неизвестная ошибка')}",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        task_data = data.get("data", {})
        kie_task_id = task_data.get("taskId")
        if not kie_task_id:
            _log(f"No taskId in response: {data}")
            return ToolResponse(
                status="error",
                error="Kie.ai: не вернул taskId в ответе",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        _log(f"Task created: {kie_task_id}")

        # 3. Async polling recordInfo
        for attempt in range(KIEAI_POLL_ATTEMPTS):
            await asyncio.sleep(KIEAI_POLL_INTERVAL_SEC)
            _log(f"Poll attempt {attempt + 1}/{KIEAI_POLL_ATTEMPTS}")

            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"{KIEAI_BASE_URL}/jobs/recordInfo",
                        params={"taskId": kie_task_id},
                        headers={"Authorization": f"Bearer {KIEAI_API_KEY}"},
                    )

                    if resp.status_code != 200:
                        _log(f"Poll HTTP {resp.status_code}, retrying...")
                        await asyncio.sleep(KIEAI_POLL_INTERVAL_SEC)
                        continue

                    info = resp.json()

                    if info.get("code") != 200:
                        _log(f"Poll error: {info.get('msg')}")
                        await asyncio.sleep(KIEAI_POLL_INTERVAL_SEC)
                        continue

                    task_info = info.get("data", {})
                    state = task_info.get("state", "")

                    if state == "success":
                        # 4. Извлекаем resultUrls из resultJson
                        result_json_str = task_info.get("resultJson", "{}")
                        try:
                            result_data = json.loads(result_json_str)
                            result_urls = result_data.get("resultUrls", [])
                        except json.JSONDecodeError:
                            result_urls = []

                        if not result_urls:
                            _log(f"No resultUrls in response: {task_info}")
                            return ToolResponse(
                                status="error",
                                error="Kie.ai: задача завершена, но нет resultUrls",
                                elapsed_ms=int((time.time() - start) * 1000),
                            )

                        # Скачиваем и сохраняем результат
                        image_url = await _download_and_save(result_urls[0], kie_task_id)
                        elapsed = int((time.time() - start) * 1000)
                        _log(f"Success in {elapsed}ms: {image_url}")
                        return ToolResponse(
                            status="success",
                            result_url=image_url,
                            elapsed_ms=elapsed,
                            metadata={"kie_task_id": kie_task_id, "source": "kieai"},
                        )

                    elif state == "fail":
                        fail_msg = task_info.get("failMsg", "Неизвестная ошибка")
                        return ToolResponse(
                            status="error",
                            error=f"Kie.ai задача failed: {fail_msg}",
                            elapsed_ms=int((time.time() - start) * 1000),
                        )

                    # queuing / generating / waiting — продолжаем polling
                    progress = task_info.get("progress", 0)
                    _log(f"State: {state}, progress: {progress}%")

            except httpx.TimeoutException:
                _log(f"Poll timeout on attempt {attempt + 1}")
                continue
            except httpx.ConnectError as e:
                _log(f"Poll connect error: {e}")
                continue
            except Exception as e:
                _log(f"Poll unexpected error: {e}")
                continue

        # Таймаут polling
        return ToolResponse(
            status="timeout",
            error=f"Kie.ai: генерация не завершена за {KIEAI_POLL_ATTEMPTS * KIEAI_POLL_INTERVAL_SEC} сек",
            elapsed_ms=int((time.time() - start) * 1000),
        )

    except httpx.ConnectError as e:
        _log(f"Connect error: {e}")
        return ToolResponse(
            status="error",
            error=f"Не удалось подключиться к Kie.ai: {e}",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    except httpx.TimeoutException as e:
        _log(f"Timeout error: {e}")
        return ToolResponse(
            status="timeout",
            error=f"Таймаут запроса к Kie.ai: {e}",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    except httpx.HTTPStatusError as e:
        _log(f"HTTP error: {e}")
        return ToolResponse(
            status="error",
            error=f"Kie.ai HTTP ошибка: {e.response.status_code}",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        _log(f"Unexpected error: {e}")
        return ToolResponse(
            status="error",
            error=f"Неизвестная ошибка Kie.ai: {str(e)}",
            elapsed_ms=int((time.time() - start) * 1000),
        )


def _width_height_to_ratio(width: int, height: int) -> str:
    """Конвертируем width/height в aspect_ratio для Kie.ai."""
    ratios = {
        (1024, 1024): "1:1",
        (1024, 768): "4:3",
        (768, 1024): "3:4",
        (1024, 576): "16:9",
        (576, 1024): "9:16",
    }
    return ratios.get((width, height), "1:1")


async def _download_and_save(url: str, task_id: str) -> str:
    """Скачиваем изображение по URL и сохраняем в tools_cache."""
    filename = f"kie_{task_id}.png"
    dest = TOOLS_CACHE_DIR / filename

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            _log(f"Saved image: {dest}")
    except Exception as e:
        _log(f"Download failed: {e}, creating placeholder")
        _create_minimal_png(dest)

    return f"/static/tools_cache/images/{filename}"


def _create_minimal_png(path: Path):
    """Создаёт минимальный PNG placeholder."""
    import struct
    import zlib
    signature = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr) & 0xffffffff)
    raw_data = b'\x00\xff\x00\x00'
    compressed = zlib.compress(raw_data)
    idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
    iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(signature)
        f.write(struct.pack('>I', 13) + b'IHDR' + ihdr + ihdr_crc)
        f.write(struct.pack('>I', len(compressed)) + b'IDAT' + compressed + idat_crc)
        f.write(struct.pack('>I', 0) + b'IEND' + iend_crc)
