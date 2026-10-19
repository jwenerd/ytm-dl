"""Gemini REST client using requests for generating AI listening reports."""

import logging
import os
import re

import requests

from src.reports.prompt import build_report_prompt, generate_fallback_report

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
)


def get_google_ai_api_key(env_path: str = ".env") -> str | None:
    """
    Retrieves the GOOGLE_AI_API_KEY from os.environ, falling back to reading
    the local .env file (handling both 'export KEY=val' and 'KEY=val').
    """
    key = os.environ.get("GOOGLE_AI_API_KEY")
    if key and key.strip():
        return key.strip()

    if os.path.isfile(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = re.match(r"^(?:export\s+)?GOOGLE_AI_API_KEY\s*=\s*(.+)$", line)
                    if m:
                        val = m.group(1).strip().strip("\"'")
                        if val:
                            return val
        except OSError as e:
            logger.warning("Could not read %s: %s", env_path, e)

    return None


def clean_markdown_fences(text: str) -> str:
    """Strips outer markdown fences if the model wrapped its entire output in ```markdown ... ```."""
    stripped = text.strip()
    if stripped.startswith("```markdown") and stripped.endswith("```"):
        stripped = stripped[len("```markdown") : -3].strip()
    elif stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
    return stripped + "\n"


def generate_report(
    context: dict,
    api_key: str | None = None,
    timeout: int = 45,
) -> str:
    """
    Generates a markdown report using Gemini 2.5 Flash via REST API.
    Gracefully falls back to deterministic markdown generation if the API key
    is missing or if the API call encounters an error.
    """
    if api_key is None:
        api_key = get_google_ai_api_key()

    if not api_key:
        logger.info(
            "GOOGLE_AI_API_KEY not found. Generating deterministic fallback report for %s.",
            context.get("period_label"),
        )
        return generate_fallback_report(context)

    prompt = build_report_prompt(context)

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 2048,
        },
    }

    try:
        resp = requests.post(
            GEMINI_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                raw_text = parts[0]["text"]
                return clean_markdown_fences(raw_text)

        logger.warning(
            "Gemini response missing candidate parts. Falling back to deterministic report."
        )
        return generate_fallback_report(context)

    except requests.RequestException as e:
        logger.warning(
            "Gemini API request failed (%s). Generating fallback report.",
            e,
        )
        return generate_fallback_report(context)
