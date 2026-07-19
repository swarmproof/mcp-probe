# mcp-probe demo

The two things no other tool shows in a CI gate: the **toolset token number** and the
**disambiguation matrix**. Captured from real runs against the repo's fixture servers.
To record a GIF: `asciinema rec demo.cast -c "bash scripts/demo.sh" && agg demo.cast demo.gif`.

## 1. The token tax — what every agent pays just to *see* your tools

```console
$ mcp-probe run "python tests/servers/bloated_server.py" --fail-under B
╭─────────────────────────────────╮
│ MCP Quality Score  81   Grade B │
╰─────────────────────────────────╯
┏━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Family      ┃  Grade  ┃   Score ┃   Weight ┃ Headline                                ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Cost        │    D    │      69 │      60% │ 8792 toolset tokens; $0.0264/task       │
│ Contract    │    A    │     100 │      40% │ 30 tools conform                        │
└─────────────┴─────────┴─────────┴──────────┴─────────────────────────────────────────┘
```

30 tools that all *work* — but they cost **8,792 tokens** on every single turn, before the
agent does anything. That number is invisible until something like this prints it.

## 2. The disambiguation matrix — which tools do agents confuse?

```console
$ mcp-probe run "python tests/servers/confusable_server.py" \
    --legibility --model ollama:mistral-small:latest --allow-writes
╭─────────────────────────────────╮
│ MCP Quality Score  67   Grade D │
╰─────────────────────────────────╯
⚠ hard-gate: 'legibility' capped the overall grade at C
┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Family     ┃ Grade ┃ Score ┃ Weight ┃ Headline                                       ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Cost       │   A   │   100 │    40% │ 122 toolset tokens; $0.0004/task               │
│ Legibility │   F   │     0 │    33% │ 50% right-tool selection;                      │
│            │       │       │        │ archive_record⇄delete_record 100%              │
│ Contract   │   A   │   100 │    27% │ 2 tools conform                                │
└────────────┴───────┴───────┴────────┴────────────────────────────────────────────────┘

Top findings
  [high] legibility/L2-confusion  agents chose 'delete_record' when 'archive_record'
                                  was correct 100% of the time
      ↳ disambiguate the two descriptions (see proposed rewrite)
  [low]  legibility/L5-rewrite  'archive_record' is hard to select; a clearer description
      ↳ proposed: Remove a record by its ID using `delete_record`. Use `archive_record`
        to move a record to the archive without deleting it.

Disambiguation matrix  (row = correct tool · cell = % of times chosen)
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ correct ↓ / chose → ┃ delete ┃ archiv ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│ delete_record       │   100% │      · │
│ archive_record      │   100% │     0% │
└─────────────────────┴────────┴────────┘
```

Two tools with the description *"Remove a record by id."* A real model (`mistral-small`
via Ollama) picked **`delete_record` 100% of the time — even when `archive_record` was the
right call.** That's a data-loss bug waiting to happen, caught before shipping — and
mcp-probe even proposes the rewrite that fixes it.

## 3. In CI

```yaml
- run: pip install mcp-probe
- run: mcp-probe run "python my_server.py" --fail-under B --no-regressions
```

See the [leaderboard](./leaderboard.md) for these checks run against real public MCP servers.
