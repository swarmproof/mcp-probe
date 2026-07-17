"""Config precedence unit tests — flags > file > env > default (TEST-PLAN §7)."""

from __future__ import annotations

from pathlib import Path

from mcp_probe.config import load_config


def test_default_is_fast_path():
    cfg = load_config()
    assert cfg.families == ("contract", "cost")
    assert cfg.allow_writes is False


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("MCP_PROBE_SEED", "99")
    monkeypatch.setenv("MCP_PROBE_ALLOW_WRITES", "true")
    cfg = load_config(cwd=Path("/nonexistent"))
    assert cfg.seed == 99
    assert cfg.allow_writes is True


def test_file_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_PROBE_SEED", "99")
    (tmp_path / ".mcp-probe.toml").write_text("seed = 7\nconcurrency = 25\n")
    cfg = load_config(cwd=tmp_path)
    assert cfg.seed == 7  # file beats env
    assert cfg.concurrency == 25


def test_flags_override_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_PROBE_SEED", "99")
    (tmp_path / ".mcp-probe.toml").write_text("seed = 7\n")
    cfg = load_config(cli_overrides={"seed": 123}, cwd=tmp_path)
    assert cfg.seed == 123  # flag wins


def test_unset_flag_does_not_clobber(tmp_path):
    (tmp_path / ".mcp-probe.toml").write_text("seed = 7\n")
    cfg = load_config(cli_overrides={"seed": None}, cwd=tmp_path)
    assert cfg.seed == 7  # None override ignored → file value survives


def test_tool_section_form(tmp_path):
    (tmp_path / ".mcp-probe.toml").write_text("[tool.mcp-probe]\nseed = 55\n")
    cfg = load_config(cwd=tmp_path)
    assert cfg.seed == 55
