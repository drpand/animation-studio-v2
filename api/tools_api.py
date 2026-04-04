"""
Tools API — REST эндпоинты для внешних инструментов.
Префикс роутов задаётся в main.py: /api/tools

Flow: Kie.ai (primary) → ComfyUI (fallback) → error
"""
import html

from fastapi import APIRouter
from pydantic import BaseModel

from tools.base_tool import rate_limiter
from tools.comfyui_tool import generate_image as comfyui_generate, check_health as comfyui_health
from tools.kieai_tool import generate_image as kieai_generate, check_health as kieai_health
from tools.elevenlabs_tool import generate_audio, list_voices
from config import MAX_PROMPT_LENGTH

router = APIRouter()


class ImageGenRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg_scale: float = 7.0
    seed: int = -1


class AudioGenRequest(BaseModel):
    text: str
    voice_id: str = ""
    model: str = "eleven_multilingual_v2"


@router.get("/health/comfyui")
async def health_check_comfyui():
    """Health-check ComfyUI."""
    healthy = await comfyui_health()
    return {"service": "comfyui", "status": "ok" if healthy else "unavailable"}


@router.get("/health/kieai")
async def health_check_kieai():
    """Health-check Kie.ai."""
    healthy = await kieai_health()
    return {"service": "kieai", "status": "ok" if healthy else "unavailable"}


@router.post("/generate-image")
async def generate_image_endpoint(req: ImageGenRequest):
    """Art Director → Kie.ai (primary) → ComfyUI (fallback) → изображение."""
    allowed, wait = rate_limiter.is_allowed()
    if not allowed:
        return {"status": "rate_limited", "error": f"Подождите {wait} сек", "retry_after": wait}

    prompt = req.prompt.strip()
    if not prompt:
        return {"status": "error", "error": "Пустой промпт"}
    if len(prompt) > MAX_PROMPT_LENGTH:
        return {"status": "error", "error": f"Промпт {len(prompt)} > {MAX_PROMPT_LENGTH} символов"}

    # 1. Пробуем Kie.ai (стабильный облачный)
    result = await kieai_generate(
        prompt=prompt,
        negative_prompt=req.negative_prompt,
        width=req.width,
        height=req.height,
        steps=req.steps,
        cfg_scale=req.cfg_scale,
        seed=req.seed,
    )

    # 2. Fallback на ComfyUI если Kie.ai failed
    if result.status in ("error", "timeout"):
        print(f"[Tools API] Kie.ai failed ({result.error}), trying ComfyUI fallback...")
        result = await comfyui_generate(
            prompt=prompt,
            negative_prompt=req.negative_prompt,
            width=req.width,
            height=req.height,
            steps=req.steps,
            cfg_scale=req.cfg_scale,
            seed=req.seed,
        )
        if result.status == "success":
            result.metadata["fallback"] = "comfyui"

    return result.to_dict()


@router.get("/test-kieai")
async def test_kieai():
    """Тестовый эндпоинт для проверки Kie.ai интеграции."""
    print("[Tools API] Test Kie.ai endpoint called")
    healthy = await kieai_health()
    return {
        "service": "kieai",
        "health": "ok" if healthy else "unavailable",
        "api_key_configured": bool(__import__("config").KIEAI_API_KEY),
        "message": "Kie.ai integration test" if healthy else "Kie.ai недоступен",
    }


@router.post("/generate-audio")
async def generate_audio_endpoint(req: AudioGenRequest):
    """Sound Director → ElevenLabs → аудио."""
    allowed, wait = rate_limiter.is_allowed()
    if not allowed:
        return {"status": "rate_limited", "error": f"Подождите {wait} сек", "retry_after": wait}

    text = req.text.strip()
    if not text:
        return {"status": "error", "error": "Пустой текст"}
    if len(text) > MAX_PROMPT_LENGTH:
        return {"status": "error", "error": f"Текст {len(text)} > {MAX_PROMPT_LENGTH} символов"}

    result = await generate_audio(text=text, voice_id=req.voice_id, model=req.model)
    return result.to_dict()


@router.get("/voices")
async def get_voices():
    """Список доступных голосов ElevenLabs."""
    voices = await list_voices()
    return {"voices": voices}


@router.get("/status")
async def tools_status():
    """Статус всех инструментов."""
    comfyui = await comfyui_health()
    kieai = await kieai_health()
    usage = rate_limiter.get_usage()
    return {
        "kieai": "ok" if kieai else "unavailable",
        "comfyui": "ok" if comfyui else "unavailable",
        "elevenlabs": "ok" if __import__("config").ELEVENLABS_API_KEY else "not_configured",
        "rate_limit": usage,
    }
