# GitHub MCP Agent Tooling

This directory contains project-local, agent-only tooling that lets Pi use GitHub MCP for safe branch and draft-PR workflows.

It is intentionally **not** part of the production FastAPI runtime and should not be registered as an always-loaded global Pi package.

## Environment

Set credentials in your shell or an ignored local environment file. Never commit token values.

Required:

```bash
export GITHUB_TOKEN="<fine-grained-token>"
export GITHUB_OWNER="<owner-or-org>"
export GITHUB_REPO="<repo-name>"
```

The wrapper passes both `GITHUB_TOKEN` and `GITHUB_PERSONAL_ACCESS_TOKEN` to the GitHub MCP server for compatibility with server versions.

Recommended fine-grained token permissions for the initial rollout:

- Metadata: read
- Contents: read/write
- Pull requests: read/write

Avoid admin, delete, workflow, organization, and secrets scopes unless a future approved plan explicitly requires them.

## Server launch

By default the wrapper launches the official container over stdio:

```text
docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN -e GITHUB_TOKEN ghcr.io/github/github-mcp-server
```

Override if needed:

```bash
export GITHUB_MCP_COMMAND="github-mcp-server"
export GITHUB_MCP_ARGS="stdio"
```

## Usage

Install agent-only dependencies:

```bash
cd backend
uv sync --group agent
```

Run preflight in dry-run mode:

```bash
uv run --group agent mirai-github-mcp preflight
```

Write commands default to dry-run and require `--apply` plus confirmation:

```bash
uv run --group agent mirai-github-mcp create-branch --branch pi/example-task
uv run --group agent mirai-github-mcp create-branch --branch pi/example-task --apply --yes
```

## Safety model

The wrapper:

- starts/connects to GitHub MCP only for one operation;
- closes the connection immediately afterwards;
- allowlists only inspect, branch, compare, draft PR, and own-PR workflows;
- rejects destructive tool names;
- rejects unsafe branch names unless they use `pi/<slug>`;
- rejects protected paths such as `data/`, `backend/mlruns/`, `backend/data-minio/`, `legacy/`, `.env*`, and key files;
- rejects secret-like PR titles/bodies;
- defaults to dry-run for writes.

Pi should invoke this tooling only when the user explicitly asks for branch, PR, GitHub issue, release, or remote compare work.
