"""Ollama model queries and image encoding."""

import json
import base64
from urllib.request import urlopen, Request


def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def query_ollama(cfg, prompt, image_paths=None, *, temperature=None, format_=None):
    """Send a prompt (+ optional images) to Ollama and return the text."""
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
    try:
        resp = urlopen(req, timeout=120)
        result = json.loads(resp.read())
        return result.get("response", "")
    except Exception as e:
        print(f"⚠️  Ollama query failed: {e}")
        return None
