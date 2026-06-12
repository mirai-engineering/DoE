# Safe GitHub PR Workflow for Pi

Use this recipe only when the user explicitly asks Pi to create or prepare a GitHub branch/PR.

## 1. Confirm intent

Ask or confirm:

- target base branch, usually `main`;
- task slug for a `pi/<task-slug>` branch;
- whether the PR should be draft, default yes;
- whether the user wants a dry run or an actual GitHub write.

## 2. Inspect local state

From the repo root:

```bash
git status --short
git branch --show-current
```

From `backend/`, run:

```bash
uv run --group agent mirai-github-mcp preflight
```

If there are local changes, summarize them. Do not continue to writes unless the user explicitly approves handling a dirty tree.

## 3. Refuse protected paths

Never include these paths in automated branch/PR changes unless a future approved plan explicitly changes the policy:

- `data/`
- `backend/mlruns/`
- `backend/data-minio/`
- `legacy/`
- `.env*`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`
- any file or text containing secret-like values

## 4. Create a safe branch

Use only a Pi-prefixed branch name:

```bash
cd backend
uv run --group agent mirai-github-mcp create-branch --branch pi/<task-slug>
```

Review the dry-run output. For actual creation, ask the user for explicit approval, then run:

```bash
uv run --group agent mirai-github-mcp create-branch --branch pi/<task-slug> --apply --yes
```

## 5. Commit only reviewed files

Before committing:

```bash
git diff --stat
git diff -- <paths>
```

Only stage files that were reviewed and are not protected:

```bash
git add <reviewed-paths>
git commit -m "<clear message>"
```

Never use broad staging like `git add .` when protected/generated paths exist.

## 6. Compare branch

Dry run first:

```bash
cd backend
uv run --group agent mirai-github-mcp compare --head pi/<task-slug>
```

Use `--apply` only if live remote comparison is needed and approved.

## 7. Create a draft PR

Dry run first:

```bash
cd backend
uv run --group agent mirai-github-mcp create-draft-pr \
  --head pi/<task-slug> \
  --title "<PR title>" \
  --body "<summary, tests, risks>"
```

After the user approves the exact PR title/body:

```bash
uv run --group agent mirai-github-mcp create-draft-pr \
  --head pi/<task-slug> \
  --title "<PR title>" \
  --body "<summary, tests, risks>" \
  --apply --yes
```

## 8. Required PR body sections

Include:

- Summary
- Changed files
- Tests run
- Safety checks
- Known risks / follow-ups

Do not include tokens, credentials, private URLs, or raw environment dumps.

## 9. Never do these through the wrapper

- force-push;
- delete branches;
- merge PRs;
- publish a draft PR as ready for review;
- modify GitHub secrets;
- modify GitHub Actions/workflows;
- perform admin operations.

Ask the user to perform those actions manually or request a separate approved plan.
