"""Ollama model queries and image encoding."""

import json
import base64
import time
from urllib.request import urlopen, Request


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def query_ollama(cfg, prompt, image_paths=None, *, temperature=None,
                 format_=None, return_timing=False):
    """Send a prompt (+ optional images) to Ollama and return the text.

    When `return_timing=True`, returns a (response_text, elapsed_ms)
    tuple instead of just response_text. On failure with timing,
    returns (None, elapsed_ms).
    """
    url = f"{cfg['ollama_url']}/api/generate"
    payload = {
        "model": cfg["ollama_model"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": cfg.get("ollama_keep_alive", "30s"),
    }
    if image_paths:
        payload["images"] = [encode_image(p) for p in image_paths]
    if temperature is not None:
        payload["options"] = {"temperature": temperature}
    if format_ is not None:
        payload["format"] = format_

    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        resp = urlopen(req, timeout=120)
        result = json.loads(resp.read())
        text = result.get("response", "")
        if return_timing:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return (text, elapsed_ms)
        return text
    except Exception as e:
        print(f"⚠️  Ollama query failed: {e}")
        if return_timing:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return (None, elapsed_ms)
        return None
