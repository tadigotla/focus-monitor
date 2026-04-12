# tests/data/screenshots

Deterministic fixture files used by tests for `focusmonitor.screenshots` and
for Ollama cassette capture.

These are real 1x1 PNGs, one per primary color. They are small (~68 bytes
each) and genuinely decodable — `llama3.2-vision` runs against them
during cassette capture, so they have to survive a real image decoder.

| File                            | Bytes | Pixel             |
|---------------------------------|------:|-------------------|
| `screen_20260412_100000.png`    |    69 | 1x1 red           |
| `screen_20260412_100100.png`    |    69 | 1x1 green         |
| `screen_20260412_100200.png`    |    69 | 1x1 blue          |

They are not meant to represent realistic screenshots — the model's
classification of "a red pixel" is meaningless. What matters is that the
byte stream is stable and the model produces a reproducible response
that vcrpy can capture, and that no real developer activity ever leaks
into a committed cassette.

`TestDeduplicateScreenshots` does NOT use these fixtures — it generates
its own differently-sized files under `tmp_path` so it can assert
specific dedup-threshold behaviour without depending on fixture sizes.

## Regeneration

If you ever need to rebuild these (changed format, corrupted, etc.), use
the helper at the bottom of `tests/data/screenshots/make_fixtures.py`
(create that script only if you need it). The generation is pure stdlib
(`struct` + `zlib`) and deterministic.
