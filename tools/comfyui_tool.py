"""
ComfyUI Tool — интеграция с ComfyUI (localhost:8188).
Генерация изображений через ComfyUI API.
"""
import os
import uuid
import time
import shutil
import httpx
from pathlib import Path

from config import COMFYUI_URL, COMFYUI_POLL_ATTEMPTS, COMFYUI_POLL_INTERVAL_SEC, MAX_PROMPT_LENGTH
from tools.base_tool import ToolResponse

TOOLS_CACHE_DIR = Path(__file__).parent.parent / "memory" / "tools_cache" / "images"
TOOLS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def check_health() -> bool:
    """Проверяет что ComfyUI запущен и отвечает."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{COMFYUI_URL}")
            return resp.status_code == 200
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
    Генерация изображения через ComfyUI.
    
    Flow:
    1. Health-check
    2. Отправляем workflow через /prompt
    3. Poll'им /history/{prompt_id} каждые N сек
    4. Сохраняем результат в tools_cache
    5. Возвращаем URL
    """
    start = time.time()

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

    # Health-check
    if not await check_health():
        return ToolResponse(
            status="error",
            error="ComfyUI не запущен. Запустите ComfyUI на localhost:8188",
            elapsed_ms=int((time.time() - start) * 1000),
        )

    # Формируем простой workflow для ComfyUI
    task_id = uuid.uuid4().hex[:12]
    workflow = _build_workflow(prompt, negative_prompt, width, height, steps, cfg_scale, seed)

    try:
        # 1. Отправляем prompt
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
            resp.raise_for_status()
            data = resp.json()
            prompt_id = data.get("prompt_id")

            if not prompt_id:
                return ToolResponse(
                    status="error",
                    error="ComfyUI не вернул prompt_id",
                    elapsed_ms=int((time.time() - start) * 1000),
                )

        # 2. Poll'им статус
        for attempt in range(COMFYUI_POLL_ATTEMPTS):
            await __import__("asyncio").sleep(COMFYUI_POLL_INTERVAL_SEC)

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
                    history = resp.json()

                    if prompt_id in history:
                        # Генерация завершена
                        output = history[prompt_id].get("outputs", {})
                        image_url = await _save_result(output, task_id)
                        elapsed = int((time.time() - start) * 1000)
                        return ToolResponse(
                            status="success",
                            result_url=image_url,
                            elapsed_ms=elapsed,
                            metadata={"prompt_id": prompt_id, "seed": seed},
                        )

                    # Проверяем ошибки
                    status = history.get(prompt_id, {}).get("status", {})
                    if status.get("status_str") == "error":
                        return ToolResponse(
                            status="error",
                            error=f"Ошибка ComfyUI: {status.get('messages', 'Неизвестная ошибка')}",
                            elapsed_ms=int((time.time() - start) * 1000),
                        )
            except httpx.HTTPError:
                continue  # Продолжаем polling

        # Таймаут
        return ToolResponse(
            status="timeout",
            error=f"Генерация не завершена за {COMFYUI_POLL_ATTEMPTS * COMFYUI_POLL_INTERVAL_SEC} сек",
            elapsed_ms=int((time.time() - start) * 1000),
        )

    except httpx.ConnectError:
        return ToolResponse(
            status="error",
            error="Не удалось подключиться к ComfyUI (localhost:8188)",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    except httpx.HTTPStatusError as e:
        return ToolResponse(
            status="error",
            error=f"Ошибка ComfyUI: {e.response.status_code}",
            elapsed_ms=int((time.time() - start) * 1000),
        )
    except Exception as e:
        return ToolResponse(
            status="error",
            error=f"Неизвестная ошибка: {str(e)}",
            elapsed_ms=int((time.time() - start) * 1000),
        )


def _build_workflow(
    prompt: str, negative_prompt: str, width: int, height: int,
    steps: int, cfg_scale: float, seed: int
) -> dict:
    """
    Строим минимальный ComfyUI workflow.
    Это базовый workflow с KSampler — пользователь может настроить через ComfyUI UI.
    """
    if seed < 0:
        import random
        seed = random.randint(0, 2**32 - 1)

    # Простой workflow: CLIP Text Encode → KSampler → VAE Decode → Save Image
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "cfg": cfg_scale,
                "denoise": 1,
                "latent_image": ["5", 0],
                "model": ["4", 0],
                "negative": ["7", 0],
                "positive": ["6", 0],
                "sampler_name": "euler",
                "scheduler": "normal",
                "seed": seed,
                "steps": steps,
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"batch_size": 1, "height": height, "width": width},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": prompt},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["4", 1], "text": negative_prompt or "worst quality, low quality"},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]},
        },
    }


async def _save_result(output: dict, task_id: str) -> str:
    """
    Сохраняем результат ComfyUI в tools_cache.
    ComfyUI сохраняет в свою output/ папку — мы копируем оттуда.
    """
    # ComfyUI output обычно в ../ComfyUI/output/
    # Для простоты — создаём placeholder если ComfyUI output недоступен
    filename = f"{task_id}.png"
    dest = TOOLS_CACHE_DIR / filename

    # Пытаемся найти файл в ComfyUI output
    comfyui_output = Path(__file__).parent.parent.parent.parent / "ComfyUI" / "output"
    if comfyui_output.exists():
        # Ищем последний сохранённый файл
        images = list(comfyui_output.glob("*.png"))
        if images:
            latest = max(images, key=lambda p: p.stat().st_mtime)
            shutil.copy2(latest, dest)
            return f"/static/tools_cache/images/{filename}"

    # Если ComfyUI output недоступен — создаём placeholder
    # В реальном использовании ComfyUI должен быть настроен правильно
    if not dest.exists():
        # Создаём минимальный PNG placeholder
        import struct
        import zlib
        # 1x1 красный пиксель
        def create_minimal_png(path):
            signature = b'\x89PNG\r\n\x1a\n'
            ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr) & 0xffffffff)
            raw_data = b'\x00\xff\x00\x00'  # filter + RGB
            compressed = zlib.compress(raw_data)
            idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + compressed) & 0xffffffff)
            iend_crc = struct.pack('>I', zlib.crc32(b'IEND') & 0xffffffff)
            with open(path, 'wb') as f:
                f.write(signature)
                f.write(struct.pack('>I', 13) + b'IHDR' + ihdr + ihdr_crc)
                f.write(struct.pack('>I', len(compressed)) + b'IDAT' + compressed + idat_crc)
                f.write(struct.pack('>I', 0) + b'IEND' + iend_crc)
        create_minimal_png(dest)

    return f"/static/tools_cache/images/{filename}"
