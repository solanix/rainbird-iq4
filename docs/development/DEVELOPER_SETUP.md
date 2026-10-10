# Development Environment and Commands

## Existing developer environment

- Host: Debian 13 Linux; VS Code + Dev Containers (Codex and Claude Code have both been used).
- Host workspace previously reported: `~/development/rainbird-iq4`.
- Container repos: `/workspaces/home-assistant-core`, `/workspaces/pyrainbird-iq4`, `/workspaces/ha-rainbird-iq4`.
- Python HA runtime: `/home/vscode/.local/ha-venv/bin/python` (Python 3.14.5, Home Assistant `2026.10.0.dev0` from the Core checkout). `python3` inside the container resolves to this venv; `pyrainbird-iq4` is installed editable into it.
- The integration is bind-mounted at `/workspaces/home-assistant-core/config/custom_components/rainbird_iq4`.
- Home Assistant frontend: `http://localhost:8123`.

## Run HA development server

```bash
cd /workspaces/home-assistant-core
/home/vscode/.local/ha-venv/bin/python -m homeassistant -c ./config
```

Stop with `Ctrl+C`. Restart fully after Python library or custom integration changes (including new actions); do not assume hot reload updates modules.

## Integration logging

In `/workspaces/home-assistant-core/config/configuration.yaml`, merge into **one** `logger:` section:

```yaml
logger:
  default: warning
  logs:
    custom_components.rainbird_iq4: info
    pyrainbird_iq4: warning
```

Temporary focused debugging:

```yaml
logger:
  default: warning
  logs:
    custom_components.rainbird_iq4: debug
    pyrainbird_iq4.local: debug
```

Reduce debugging again after a bounded capture because of disk usage. Logs can contain device metadata; redact before sharing. Do not log passwords/tokens. Control writes log at `info` (library, acknowledged) and `warning` (ambiguous or unconfirmed).

## Read-only diagnostics

**Stop HA local polling before standalone local diagnostics** if session contention is possible.

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10
python3 -m pyrainbird_iq4.local_diagnostic 192.0.2.10 --check-control-support
```

Do not run `--write-test` as part of ordinary development workflows or automated tests.

## Quality gates

```bash
cd /workspaces/pyrainbird-iq4
python3 -m pytest
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src

cd /workspaces/ha-rainbird-iq4
python3 -m pytest                 # tests/ against HA stubs
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy .                 # type-checks custom_components against the real HA package

cd /workspaces/home-assistant-core  # tests_ha/ against real HA; must run from Core
python3 -m pytest -c pyproject.toml -p tests.conftest /workspaces/ha-rainbird-iq4/tests_ha
```

Latest results (2026-10-10): library 105; integration stub suite 73; real-HA suite 56; all lint/format/type checks clean.

### Why two integration suites

`tests/` puts `tests/stubs` first on `pythonpath`, so `homeassistant` there is a hand-written stand-in. It is fast but cannot prove anything about real HA behaviour (admin authorization, service schemas, device registry, entry lifecycle). `tests_ha/` loads Core's own pytest plugin (`-p tests.conftest`) and `MockConfigEntry`, and prepends this repository's `custom_components` directory to the package path at import time so HA loads this integration ahead of Core's test custom components. No Core files are modified. When a module in `custom_components` gains a new HA import, the stub suite may need a matching minimal stub.

## Git working tree

Phase 2A–2C is committed on `master` in both repositories (no remotes configured). Build artifacts (`__pycache__`, `*.egg-info`) are ignored in both.

Check before acting:

```bash
cd /workspaces/pyrainbird-iq4 && git status --short && git diff --stat
cd /workspaces/ha-rainbird-iq4 && git status --short && git diff --stat
```

Commit each repository separately **only upon explicit user request**. Do not edit `/workspaces/home-assistant-core` production source.
