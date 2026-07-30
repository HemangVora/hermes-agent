---
name: forge-tasks
description: "USE THIS whenever the user asks to build, add, change, fix, or review code in a GitHub repository. Forge clones, edits, commits and pushes a branch for you — do not clone or use gh yourself."
version: 1.0.0
author: HemangVora
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Forge, Coding, Automation, Git, Branch, CI]
    related_skills: [github-pr-workflow]
prerequisites:
  commands: [curl, jq]
  env: [FORGE_API_URL, FORGE_TOKEN]
---

# Forge Tasks

Forge executes coding work asynchronously. You submit a task, it clones the
repository, runs an AI coding provider against it, commits the result, and
pushes a branch. You report progress back to the user.

## Read this first

**Any request to build, add, change, fix, or review code in a GitHub
repository goes to Forge.** Do not clone the repository. Do not run `gh` or
`git`. Do not write the file locally and describe it. Those approaches fail
here for concrete reasons:

- The repositories are **private**, and this container holds no GitHub
  credential — a clone returns 404, which reads as "repo does not exist" and
  sends you down a debugging path that has no end.
- `gh` is **not installed**.
- Even a successful local edit changes nothing the user can see. Forge is what
  produces a branch they can open a pull request from.

If you have already tried cloning and got a 404, that is this situation. Stop
and submit to Forge instead of asking the user to grant access.

## When to Use

- "Build a login page in owner/repo"
- "Add a CONTRIBUTING.md to owner/repo"
- "Add tests for the auth module in owner/repo"
- "Fix the failing build in owner/repo"
- "Review the changes in owner/repo"

Any phrasing that names a repository and asks for work in it qualifies —
"build", "add", "create", "write", "change", "update", "fix", "refactor",
"review". The user does not need to say "Forge".

## When NOT to Use

- Questions about code you can answer directly — Forge takes minutes and costs
  money; do not use it as a search tool.
- Anything outside a Git repository.
- The user has not said which repository. **Ask first.** Forge needs an
  `owner/name` and will fail without one.

## Submitting

Every request needs the `X-Forge-Token` header. Without it the API returns 401.

```bash
curl -sS -X POST "$FORGE_API_URL/task" \
  -H "Content-Type: application/json" \
  -H "X-Forge-Token: $FORGE_TOKEN" \
  -d '{"repository":"owner/name","prompt":"<what the user asked, in full>"}' \
  | jq -r '.task_id'
```

Pass the user's request through as the prompt. Do not summarize it — Forge's
provider works better with the full ask, and detail you drop is detail it
cannot act on.

Tell the user the task ID immediately. Work takes minutes; silence reads as
failure.

## Following progress

```bash
curl -sS -H "X-Forge-Token: $FORGE_TOKEN" \
  "$FORGE_API_URL/tasks/<task_id>/events" \
  | jq -r '.[] | "\(.status)\t\(.stage)\t\(.progress)%\t\(.message // "")"'
```

Stages run: `queued` → `preparing` → `workspace` → `profiling` → `executing`
→ `publishing` → `collecting` → `done`. Report meaningful transitions, not
every poll. Poll about every 20 seconds; do not busy-loop.

## Finishing

```bash
curl -sS -H "X-Forge-Token: $FORGE_TOKEN" "$FORGE_API_URL/tasks/<task_id>" | jq
```

`status` is `done`, `failed`, or `cancelled`.

- **done** — report the branch name so the user can open a PR. A task can
  succeed with no branch when the provider changed nothing; say so plainly
  rather than implying work happened.
- **failed** — report the reason from the event stream. Do not retry
  automatically: a repeat costs money and most failures (bad repository,
  missing credentials, exhausted credit) will fail again identically.

## Rules

- Never invent a task ID, a branch name, or a completion. If you have not seen
  it in a response, you do not know it.
- Never claim work is done before `status` is `done`.
- One task per request. Do not fan out multiple tasks to "try approaches".
