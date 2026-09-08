# Rain Bird IQ4 for Home Assistant

Read-only Home Assistant custom integration for Rain Bird IQ4 controllers using the sibling library `pyrainbird-iq4`.

## Development setup

With `uv`, the sibling source is selected automatically by `[tool.uv.sources]`:

```bash
cd /home/user/development/rainbird-iq4/ha-rainbird-iq4
uv sync --extra dev
```

For a pip-based environment, install the sibling first and install this project
without dependency resolution so pip does not look for the unreleased package:

```bash
cd /home/user/development/rainbird-iq4
python -m pip install -e ./pyrainbird-iq4
cd ha-rainbird-iq4
python -m pip install -e . --no-deps
```

The Home Assistant manifest intentionally leaves `requirements` empty until
`pyrainbird-iq4` is published. For a local Home Assistant test, install or mount the
sibling library into the same Python environment first. No access token is persisted;
Home Assistant stores only the username, password, and selected controller ID in its
normal config entry storage.

## Isolated Home Assistant development instance

The sibling `home-assistant-core` clone is configured for the official VS Code
dev-container workflow. Its local dev-container configuration:

- bind-mounts this integration directly at
  `config/custom_components/rainbird_iq4`;
- bind-mounts `../pyrainbird-iq4` at `/workspaces/pyrainbird-iq4`; and
- installs the library editable into the Home Assistant development virtual
  environment during container creation.

From the workspace root, open Core in VS Code:

```bash
cd /home/user/development/rainbird-iq4/home-assistant-core
code .
```

Choose **Dev Containers: Rebuild and Reopen in Container**. After the setup completes,
run **Tasks: Run Task → Run Home Assistant Core**, or run this inside the container:

```bash
/home/vscode/.local/ha-venv/bin/python -m homeassistant -c ./config
```

Open <http://localhost:8123>. The first launch presents an onboarding flow for this
development-only instance. Create a local administrator there, then add **Rain Bird
IQ4** from **Settings → Devices & services → Add integration** only when ready to test
against the cloud. Do not reuse or connect this configuration directory to production
HAOS.

Before production installation, publish `pyrainbird-iq4`, add its pinned release to
`manifest.json` under `requirements`, and replace/augment repository metadata with the
real documentation and issue-tracker URLs. The current manifest deliberately makes no
claim that the library is available from PyPI.

## Scope

- Read-only cloud polling
- Controller discovery and selection
- Device metadata and sensors
- No irrigation controls, service calls, or schedule writes yet

## License

MIT
