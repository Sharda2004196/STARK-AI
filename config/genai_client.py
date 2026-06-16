# config/genai_client.py
# Unified Gemini client for google-genai SDK (new)
# Replaces deprecated google.generativeai usage

import os
import json
import time
import requests
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

import google.genai as genai
from google.genai import types

# Lazy-initialized client (created once on first use)
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Get or create the centralized Gemini client."""
    global _client
    if _client is None:
        api_key = _get_api_key()
        # Using v1beta for access to latest preview/experimental models
        _client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    return _client


def _get_api_key() -> str:
    """Load API key from config file."""
    config_path = Path(__file__).parent / "api_keys.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_opencode_api_key() -> str:
    """Load OpenCode API key from config file."""
    config_path = Path(__file__).parent / "api_keys.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            keys = json.load(f)
            return keys.get("opencode_api_key", "")
    except Exception:
        return ""


# ─── Convenience wrappers ───────────────────────────────────────────────────

# Transient HTTP status codes that should trigger a retry
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 1  # Quick safety-net retry; callers (e.g. doc_creator) handle fallback models
_RETRY_BASE_DELAY = 1.5  # seconds; doubles each attempt (1.5, 3.0, 6.0)


def _is_transient_error(exc: Exception) -> bool:
    """Return True if the exception is likely a transient server error."""
    msg = str(exc).lower()
    # Check for HTTP status codes in the error message
    for code in _RETRYABLE_STATUSES:
        if str(code) in msg:
            return True
    # Check for common transient-error keywords
    for kw in ("unavailable", "timeout", "deadline", "connection", "reset", "503"):
        if kw in msg:
            return True
    return False


def generate_content(
    model: str,
    contents,
    config: dict | None = None,
    system_instruction: str | None = None,
    provider: str = "gemini",
    _retries: int = _MAX_RETRIES,
) -> str:
    """
    Generate content using the new SDK client or custom providers like OpenCode Zen.

    Automatically retries on transient errors (503, 429, 500, etc.) with
    exponential back-off before giving up.

    Args:
        model: Model name (e.g., "gemini-2.0-flash", or "opencode/deepseek-v4-flash")
        contents: String, list, or Part objects
        config: GenerationConfig dict (temperature, max_tokens, etc.)
        system_instruction: Optional system prompt
        provider: "gemini" (default) or "opencode"

    Returns:
        Response text as string
    """
    if provider == "opencode":
        if OpenAI is None:
            raise ImportError("The 'openai' library is required for the 'opencode' provider. Please install it with 'pip install openai'.")
        
        api_key = _get_opencode_api_key()
        if not api_key or api_key == "YOUR_OPENCODE_API_KEY":
            raise ValueError("OpenCode API Key is missing or invalid in config/api_keys.json")
        
        client = OpenAI(
            base_url="https://opencode.ai/zen/v1",
            api_key=api_key
        )
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        
        # Simple extraction for strings
        if isinstance(contents, str):
            messages.append({"role": "user", "content": contents})
        elif isinstance(contents, list):
            # For simplicity with OpenCode, we extract text parts
            text_parts = []
            for item in contents:
                if isinstance(item, str):
                    text_parts.append(item)
            messages.append({"role": "user", "content": " ".join(text_parts)})
        
        params = {
            "model": model,
            "messages": messages,
            "temperature": 0.2
        }
        
        if config and "temperature" in config:
            params["temperature"] = config["temperature"]
        if config and "max_tokens" in config:
            params["max_tokens"] = config["max_tokens"]

        response = client.chat.completions.create(**params)
        return response.choices[0].message.content
    
    else:
        # Default Gemini flow — with retry for transient errors
        last_exc = None
        for attempt in range(_retries + 1):
            try:
                client = get_client()

                # Build config kwargs
                opts = {"model": model, "contents": contents}
                if config:
                    opts["config"] = config
                if system_instruction:
                    opts["config"] = {**(config or {}), "system_instruction": system_instruction}

                response = client.models.generate_content(**opts)
                return response.text
            except Exception as exc:
                last_exc = exc
                if attempt < _retries and _is_transient_error(exc):
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"[Gemini] ⚠️  {type(exc).__name__} on attempt {attempt + 1}/{_retries + 1} — retrying in {delay:.1f}s...")
                    time.sleep(delay)
                else:
                    raise
        # Should never reach here, but just in case
        raise last_exc


def generate_images(
    prompt: str,
    model: str = "imagen-3.0-generate-002",
    config: dict | None = None,
) -> bytes:
    """
    Generate an image using the Imagen model.
    """
    client = get_client()
    # The new SDK uses generate_images (plural)
    response = client.models.generate_images(
        model=model,
        prompt=prompt,
        config=config
    )
    return response.generated_images[0].image.image_bytes


def generate_videos(
    prompt: str,
    image: types.Image | None = None,
    model: str = "veo-2.0-generate-001",
    config: dict | None = None,
):
    """
    Generate a video using the Veo model.
    Returns an operation object.
    """
    client = get_client()
    # The new SDK uses generate_videos (plural)
    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        image=image,
        config=config
    )
    return operation


def get_operation(operation):
    """Retrieve the current status of a long-running operation."""
    client = get_client()
    return client.operations.get(operation.name)


def generate_content_async(
    model: str,
    contents,
    config: dict | None = None,
    system_instruction: str | None = None,
    provider: str = "gemini"
):
    """
    Async version of generate_content.
    Use with: asyncio.run(genai_client_async(...))
    """
    import asyncio

    async def _run():
        if provider == "opencode":
            # For simplicity, running the sync request in an executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, 
                lambda: generate_content(model, contents, config, system_instruction, provider="opencode")
            )
        else:
            client = get_client()
            opts = {"model": model, "contents": contents}
            if config:
                opts["config"] = config
            if system_instruction:
                opts["config"] = {**(config or {}), "system_instruction": system_instruction}
            response = await client.aio.models.generate_content(**opts)
            return response.text

    return _run()