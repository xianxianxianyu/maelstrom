"""Shared LLM client — single implementation for all protocol-based LLM calls."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def build_request(
    profile: dict[str, Any],
    prompt: str,
    *,
    max_tokens: int = 4096,
    temperature_override: float | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Build (url, headers, body) from a profile dict and prompt.

    Returns a tuple ready for ``httpx.AsyncClient.post(url, headers=headers, json=body)``.
    """
    protocol = profile.get("protocol", "openai_chat")
    base = profile.get("base_url", "https://api.openai.com/v1").rstrip("/")
    key = profile.get("api_key") or ""
    model = profile.get("model", "gpt-4o")
    temperature = temperature_override if temperature_override is not None else profile.get("temperature", 0.7)

    messages = [{"role": "user", "content": prompt}]

    if protocol == "anthropic_messages":
        url = f"{base}/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
    elif protocol == "openai_responses":
        url = f"{base}/responses"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "temperature": temperature,
            "input": prompt,
            "max_output_tokens": max_tokens,
        }
    else:  # openai_chat (default)
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }

    return url, headers, body


def extract_text(protocol: str, data: dict[str, Any]) -> str:
    """Extract the assistant's text from an API response."""
    if protocol == "anthropic_messages":
        return data["content"][0]["text"]
    if protocol == "openai_responses":
        # Responses API returns output[].content[].text
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        return part["text"]
        return ""
    # openai_chat
    return data["choices"][0]["message"]["content"]


async def call_llm(
    prompt: str,
    profile: dict[str, Any],
    *,
    max_tokens: int = 4096,
    temperature_override: float | None = None,
    timeout: float = 60.0,
) -> str:
    """One-shot LLM call. Returns the assistant's text response."""
    url, headers, body = build_request(
        profile, prompt, max_tokens=max_tokens, temperature_override=temperature_override,
    )
    protocol = profile.get("protocol", "openai_chat")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return extract_text(protocol, data)
