# mcp-privacy-guard

Claude Code plugin and local engine that pseudonymize MCP tool data and user questions before
they reach the model, and reveal real values on the user's own screen. Works with any MCP
server, with no change to the servers or to the MCP configuration.

**Status**: feature 001 is implemented (tool results, tool arguments, questions, reveal,
profiles, operator control) and tested; it has not yet been run in a live Claude Code session
(see `specs/001-mcp-pseudonymization/quickstart.md`). Treat it as a release candidate.

## How it works

The guard replaces every identifying value (addresses, host names, e-mails, names, free text)
with a stand-in before the model sees it, translates the stand-ins in the model's tool calls
back to real values, and shows you the real values in your terminal. It fails closed: what
cannot be processed is withheld, and there is no setting that turns it off. The only opt-out is
an operator exemption of one server by name.

## Requirements

- Claude Code 2.1.303 or newer, **in a terminal** (the VS Code extension and the desktop app are
  refused).
- Claude Code's **sandbox**, with the guard's folder denied to reads (exact settings in
  [`docs/install.md`](docs/install.md)).
- **Session-only stand-ins**: each session has its own secret and mapping, deleted when it ends.
  Use `/clear`, not `--resume`; a resumed conversation is blocked.
- Python 3.11 or newer for the engine (standard library only).

## Documentation

- [`docs/install.md`](docs/install.md): installation, sandbox settings, troubleshooting.
- [`docs/coverage.md`](docs/coverage.md): what is sent to the model provider, what is covered,
  blocked or not covered, and the residual risks.
- [`docs/profiles.md`](docs/profiles.md): writing a profile for a server.
- `specs/001-mcp-pseudonymization/`: specification, plan, contracts and tasks.

## Development

```sh
cd engine && uv sync && uv run pytest        # all tests; -m leak / -m bench for the gates
uv run ruff check . && uv run mypy src
claude plugin validate plugin && claude plugin test plugin
```
