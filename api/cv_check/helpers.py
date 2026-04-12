"""Shared helpers for CV check API endpoints."""
import base64
import json
import os

import httpx

from config import OPENROUTER_API_KEY, PROJECT_ROOT_CONFIG
from utils.logger import info, error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def image_to_base64(image_url: str) -> str:
    """Load image by URL and convert to base64."""
    # If local path
    if image_url.startswith("/tools_cache/"):
        filename = os.path.basename(image_url)
        local_path = os.path.join(PROJECT_ROOT, "memory", "tools_cache", "images", filename)
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        return ""

    # If external URL
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            if resp.status_code == 200:
                return base64.b64encode(resp.content).decode("utf-8")
    except Exception:
        pass
    return ""


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response."""
    import re
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {}
    return {}


def clean_unicode(text: str) -> str:
    """Clean Unicode special characters from text."""
    return (text
            .replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"'))


def to_ascii(s):
    """Convert string to ASCII, replacing non-ASCII characters."""
    if not s:
        return ""
    return str(s).encode("ascii", errors="replace").decode("ascii")


async def call_llm(system_prompt: str, user_prompt: str, model: str = "google/gemini-3.1-flash-preview") -> str:
    """Call LLM via OpenRouter."""
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 2000,
    }, ensure_ascii=True)

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:7860",
                "X-Title": "Animation Studio v2 - CV Check",
            },
            content=body.encode("utf-8"),
        )
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
