# Development Environment and Commands

## Existing developer environment

- Host: Debian 13 Linux; VS Code + Dev Containers (Codex and Claude Code have both been used).
- Host workspace previously reported: `~/development/rainbird-iq4`.
- Container repos: `/workspaces/home-assistant-core`, `/workspaces/pyrainbird-iq4`, `/workspaces/ha-rainbird-iq4`.
- Python HA runtime: `/home/vscode/.local/ha-venv/bin/python` (Python 3.14.5, Home Assistant `2026.10.0.dev0` from the Core checkout). `python3` inside the container resolves to this venv; `pyrainbird-iq4` is installed editable into it.
- The integration is bind-mounted at `/workspaces/home-assistant-core/config/custom_components/rainbird_iq4`.
- Home Assistant frontend: `http://localhost:8123`.

## Working outside the dev container

With `uv`, the sibling library is picked up through `[tool.uv.sources]`:

```bash
cd ha-rainbird-iq4
uv sync --extra dev
```

With pip, install the library first and this project without dependency resolution, so pip
does not look for the unpublished `pyrainbird-iq4` on PyPI:

```bash
python -m pip install -e ./pyrainbird-iq4
python -m pip install -e ./ha-rainbird-iq4 --no-deps
```

The manifest pins the published `pyrainbird-iq4` release; CI installs that pin. For changes
that span both repos, install the sibling editable as above and bump the pin after releasing it. Home Assistant stores only the username, password, controller ID and
local options in the config entry; no access token is persisted.

The Home Assistant Core dev container bind-mounts this repository at
`config/custom_components/rainbird_iq4` and installs the library editable. Use a separate
configuration directory for development, never a production HAOS configuration.

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
python3 -m ruff check .
python3 -m ruff format --check custom_components tests_ha
python3 -m mypy .                 # type-checks custom_components against the real HA package

cd /workspaces/home-assistant-core  # all integration tests run against real HA, from Core
python3 -m pytest -c pyproject.toml -p tests.conftest /workspaces/ha-rainbird-iq4/tests_ha
```

Card: `cd dashboard && npm test && npm run typecheck` (Node 20+, runs on the host or in the container).

Latest results (2026-10-13): library 107; integration 174 (89 setup-level in `tests_ha/`, 85 unit in `tests_ha/unit/`); card 76; all lint/format/type checks clean.

### How the integration tests run

`tests_ha/` loads Core's own pytest plugin (`-p tests.conftest`) and `MockConfigEntry`, and prepends this repository's `custom_components` directory to the package path at import time so HA loads this integration ahead of Core's test custom components. No Core files are modified.

- `tests_ha/*.py` set up whole config entries through HA with cloud fetch and local connect mocked (the autouse `mock_io` fixture): services, authorization, registries, lifecycle, the card.
- `tests_ha/unit/` tests coordinators, the local connection and entities directly. Its conftest turns `mock_io` off, because these tests mock the cloud client and local controller themselves, and removes the local retry delay and grace periods unless a test opts in (`local_grace`).

There used to be a separate suite against hand-written HA stubs (`tests/`); it was moved here and the stubs removed on 2026-10-12 (ADR-016).

## Releasing

1. Publish `pyrainbird-iq4` first if it changed (GitHub release `vX.Y.Z` in that repo runs its PyPI publish workflow), then pin it in `manifest.json` `requirements`.
2. Bump `version` in `custom_components/rainbird_iq4/manifest.json`; if the card changed, bump it as described in `dashboard/README.md`.
3. Update `docs/CHANGELOG.md`, commit, push, and wait for CI.
4. Create a GitHub release tagged `v<manifest version>`; the *Release check* workflow fails a mismatched tag. HACS (once the repository is public) offers the release as an update.

## Git working tree

Phase 2A–2C is committed on `master` in both repositories (no remotes configured). Build artifacts (`__pycache__`, `*.egg-info`) are ignored in both.

Check before acting:

```bash
cd /workspaces/pyrainbird-iq4 && git status --short && git diff --stat
cd /workspaces/ha-rainbird-iq4 && git status --short && git diff --stat
```

Commit each repository separately **only upon explicit user request**. Do not edit `/workspaces/home-assistant-core` production source.
