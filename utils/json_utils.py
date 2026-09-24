"""
json_utils.py - Robust JSON parsing helper for LLM responses (Groq, OpenAI, Claude, etc.)
Handles markdown code blocks, prose wrappers, trailing commas, control characters, and whitespace.
"""

import json
import re

def safe_json_parse(raw_text: str, default=None):
    """
    Safely parses JSON strings returned by LLMs.
    Handles markdown code blocks, leading/trailing prose, trailing commas, and whitespace.
    Never raises an exception — returns `default` (or empty dict) if parsing fails.
    """
    if default is None:
        default = {}

    if not raw_text or not isinstance(raw_text, str):
        return default

    text = raw_text.strip()

    # Strip <think>...</think> blocks from reasoning models
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Strip markdown code fences (e.g. ```json ... ```)
    if "```" in text:
        text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = text.replace("```", "").strip()

    # Find the bounds of JSON object {} or array []
    start_obj = text.find('{')
    start_arr = text.find('[')

    start = -1
    end = -1

    if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
        start = start_obj
        end = text.rfind('}')
    elif start_arr != -1:
        start = start_arr
        end = text.rfind(']')

    if start != -1 and end > start:
        text = text[start:end + 1]

    # Attempt 1: Direct json.loads
    try:
        return json.loads(text)
    except Exception:
        pass

    # Attempt 2: Clean trailing commas before closing braces/brackets
    cleaned = re.sub(r',\s*([\}\]])', r'\1', text)
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Attempt 3: Relax control character restrictions
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        return default
