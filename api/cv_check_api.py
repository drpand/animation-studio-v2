"""
CV Check API — проверка сгенерированного изображения через OpenRouter Vision.

This file is now a thin wrapper that imports from the modularized api/cv_check/ package
for backward compatibility.
"""
from api.cv_check.endpoints import (  # noqa: F401
    router,
    cv_check,
    cv_auto_fix,
    run_critic_review,
    run_fixer_rewrite,
    run_cv_check,
)
from api.cv_check.helpers import (  # noqa: F401
    image_to_base64,
    extract_json,
    clean_unicode,
    to_ascii,
    call_llm,
    PROJECT_ROOT,
)
