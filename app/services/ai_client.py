import logging
from anthropic import Anthropic
from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Anthropic | None = None


def _get_client() -> Anthropic | None:
    global _client
    if not settings.anthropic_api_key:
        return None
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def generate_text(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
) -> str | None:
    """
    Call Claude API synchronously. Returns None if key absent or on error.
    Always safe to call — callers fall back to templates when None is returned.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        kwargs: dict = {
            "model": settings.claude_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("Claude API call failed: %s", exc)
        return None


def is_available() -> bool:
    return settings.anthropic_api_key is not None
