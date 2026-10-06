# Registry / marketplace integration

How a registry or marketplace attaches a verifiable **MCP Quality Score** to a server
listing and keeps it fresh. Built on `mcp-quality serve` (the `[registry]` extra) — a
stateless, air-gapped scoring API over the offline `static` path. **No secrets** are
required: the API scores a `tools/list` dump you provide.

```bash
pip install "mcp-quality[registry]"
mcp-quality serve --host 0.0.0.0 --port 8080
```

Every response carries `rubric_version` and a `provenance_hash`, so a stored grade is
**re-verifiable** and **comparable across releases**.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | liveness + current `rubric_version` |
| `POST` | `/score` | score one server (a `tools/list` dump) → `mcp-quality/report@1` |
| `POST` | `/score/batch` | score many servers in one request (ingest) |
| `POST` | `/verify` | re-score a dump and confirm a claimed `provenance_hash` wasn't hand-edited |
| `POST` | `/freshness` | is a stored grade stale? (rubric or surface changed) |

### Score one server
```bash
curl -s localhost:8080/score -d '{"tools":[{"name":"get_weather",
  "description":"Return the weather for a city.","inputSchema":{"type":"object"}}]}'
# → { "overall": {"grade":"A","score":...}, "rubric_version":"...",
#     "provenance_hash":"sha256:...", "target":{"surface_hash":"sha256:..."} , ... }
```

### Batch ingest
```bash
curl -s localhost:8080/score/batch -d '{"servers":[
  {"id":"srv-1","tools":[ ... ]},
  {"id":"srv-2","tools":[ ... ]}
]}'
# → { "results":[{"id":"srv-1","report":{...}}, ...], "count":2, "rubric_version":"..." }
```

### Verify a badge wasn't edited
Store `provenance_hash` with the listing; re-check it on display:
```bash
curl -s localhost:8080/verify -d '{"tools":[ ... ],"provenance_hash":"sha256:..."}'
# → { "verified": true, "claimed":"sha256:...", "actual":"sha256:...", "rubric_version":"..." }
```

### Keep grades fresh
A listed grade goes stale when (a) the scoring **rubric** changes, or (b) the server's
**surface** changes. Check cheaply (no re-scoring) by re-fetching the server's current
`tools/list` and passing the stored `rubric_version` + `surface_hash`:
```bash
curl -s localhost:8080/freshness -d '{"tools":[ ...current... ],
  "rubric_version":"2026.08.1","surface_hash":"sha256:...stored..."}'
# → { "stale": true, "reasons":["server surface changed since the last score"],
#     "current_rubric_version":"...", "current_surface_hash":"sha256:..." }
```
Re-score (and re-badge) whenever `stale` is `true`.

## Reference GitHub Action

Drop this into a submitted server's repo (or run it registry-side) to gate a listing on a
minimum grade and publish the badge:

```yaml
name: mcp-quality
on: [push, pull_request]
jobs:
  score:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install mcp-quality
      # Public stdio/HTTP server → score live and gate on a grade floor:
      - run: mcp-quality run "python my_server.py" --json --fail-under B
      # Publish the badge:
      - run: mcp-quality badge "python my_server.py" --out badge.svg
      # Private server → pass an auth header (kept in a repo secret, never in the surface):
      # - run: mcp-quality run "https://mcp.example.com" --header "Authorization: Bearer ${{ secrets.MCP_TOKEN }}" --fail-under B
```

## Webhook (registry-side)

On submission, POST the server's `tools/list` to your running `serve` instance and store
`overall.grade`, `provenance_hash`, `target.surface_hash`, and `rubric_version` with the
listing. On a schedule, call `/freshness` with the stored values and re-score when stale.

> Private live servers: the scoring API itself needs no secrets. To score a private server
> you (the registry) run `mcp-quality run <url> --header '...'` on your side — the auth
> header rides the connection and never enters the scored surface or the stored report.
