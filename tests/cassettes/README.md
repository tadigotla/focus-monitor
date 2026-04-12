# tests/cassettes

vcrpy cassettes for `focusmonitor.ollama` and `focusmonitor.activitywatch`.

These are **committed to git** so a fresh clone can run the full test suite
offline. Do not delete them casually. Do not hand-edit them casually either
— the point is that they are the exact bytes captured from the real local
service on the day of capture.

## Layout

```
tests/cassettes/
├── ollama/
│   └── test_<name>.yaml
└── activitywatch/
    └── test_<name>.yaml
```

Each YAML file contains one or more request/response pairs, the capture
metadata (date, service version), and is small enough (tens of KB) to live
in git without ceremony.

## When to re-record

Re-record when any of these are true:

1. You bump `ollama_model` in `DEFAULT_CONFIG` or upgrade the Ollama binary.
2. You upgrade ActivityWatch.
3. A cassette-backed test starts failing for a reason you suspect is
   upstream drift (a field renamed, a new required header, a response shape
   change).
4. You are intentionally adding a new interaction to an existing test and
   need the real response for it.

Do NOT re-record just because a cassette "looks old." Staleness is judged
by whether the recorded bytes still reflect real service behaviour, not
by the calendar.

## How to re-record

1. Start the real service locally:
   - Ollama: `ollama serve` (or run the Ollama desktop app)
   - ActivityWatch: launch the ActivityWatch app
2. Activate the dev venv: `source .venv/bin/activate`
3. Run the target tests in rewrite mode:

   ```bash
   pytest --record-mode=rewrite -k test_ollama
   pytest --record-mode=rewrite -k test_activitywatch
   ```

4. **Review the diff** before committing. Open the changed cassette(s) in
   your editor and scan for:
   - User-identifying content from your own `~/.focus-monitor/` —
     window titles, file paths, app names, personal task names
   - API keys or auth tokens (there shouldn't be any for localhost
     services, but check anyway)
   - Anything that changed unexpectedly in the response shape

   If the cassette contains personal data, **discard it** (`git checkout
   tests/cassettes/...`) and re-record using only inputs from
   `tests/data/`.

5. Update the capture-date and service-version metadata at the top of
   each touched cassette.

6. Commit cassettes with a clear message: `tests: re-record <service>
   cassettes (model/version bump)`.

## Privacy rule (hard)

Cassettes are captured against the deterministic fixture corpus under
`tests/data/`, never against live `~/.focus-monitor/` state. If you cannot
capture a cassette without pointing the client at real user data, stop and
either change the test to use fixtures or flag the gap in an openspec
change — do not commit a cassette containing personal data.
