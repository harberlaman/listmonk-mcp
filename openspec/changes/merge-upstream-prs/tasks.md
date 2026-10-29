# Tasks

## 1. Baseline

- [x] 1.1 Run `uv sync --extra dev`, then `uv run ruff check src/ && uv run mypy src/ && uv build` on `master` and record the result. Verify: the commands' output is recorded here, so later failures can be told apart from failures that already existed.
  - Baseline (2026-10-28, `3e1cf0d`+2, uv 0.12.21): ruff "All checks passed!", mypy "Success: no issues found in 6 source files", `uv build` produced `listmonk_mcp-0.1.0` sdist and wheel.
  - NOTE: `uv sync` rewrites `uv.lock` (lock `revision` 2→3, and a stale `version = "0.0.12"` becomes `0.1.0`). Reverted so the merges apply cleanly. Commit a regenerated lock after the merges.
- [x] 1.2 Confirm the PR refs are present and unchanged upstream (`git rev-parse refs/upstream-pr/8 refs/upstream-pr/11` against `gh pr view 8 -R rhnvrm/listmonk-mcp --json headRefOid` and the same for 11). Re-fetch if they differ. Verify: the SHAs match.
  - #8 `4fd84c2`, #11 `ccd7600`, both identical to the upstream heads.

## 2. Merge PR #11 (subject carry-forward)

- [x] 2.1 `git merge --no-ff refs/upstream-pr/11 -m "Merge upstream PR #11: carry forward subject in update_template"` on `master`. Verify: `git log --oneline -3` shows the merge commit and ohm-meter's commit.
  - Merged as `cf363ff` (ohm-meter `ccd7600`).
- [x] 2.2 Create `tests/conftest.py` (a test `Config`, a `ListmonkClient` with `connect()` bypassed, and pytest-httpx fixtures) and `tests/test_templates.py`, covering the three scenarios in `specs/template-management` under "Template update preserves the existing subject". Verify: `uv run pytest tests/test_templates.py` passes.
- [x] 2.3 Run ruff, mypy and build. Verify: all pass, or any failure matches the 1.1 baseline.
  - ruff (src and tests), mypy and build all pass. pytest: 3 passed.

## 3. Review and merge PR #8 (API coverage)

- [ ] 3.1 Review `git diff master...refs/upstream-pr/8` using the design.md D2 checklist: method and path of every new endpoint against the Listmonk v6 API docs, the `test_campaign` payload, the `update_setting` raw body, `delete_bounces` treating no IDs as "all", and the separate auth client in `import_subscribers`. Verify: a `NOTE:` line is added under this task for every finding, or "no findings".
- [ ] 3.2 `git merge --no-ff refs/upstream-pr/8 -m "Merge upstream PR #8: comprehensive API coverage"`. Resolve conflicts if any appear. Verify: the merge commit exists and `pyproject.toml` says `version = "0.2.0"`.
- [ ] 3.3 Read the merged `update_template` in `client.py` and `server.py` to confirm #11's `subject` handling survived. Verify: `uv run pytest tests/test_templates.py` still passes.
- [ ] 3.4 Fix only blocking problems from 3.1 to 3.3 (build, lint or type failures, or a wrong endpoint) in a separate commit. Verify: each fix commit names the `NOTE:` it addresses, or this task is marked "none needed".
- [ ] 3.5 Add `tests/test_admin.py` for `update_setting` (the PUT body is the raw value, not `{"value": …}`) and `tests/test_campaigns.py` for the `test_campaign` payload (saved campaign fields plus `subscribers`). Verify: `uv run pytest` passes.
- [ ] 3.6 Add `tests/test_bounces.py` for `delete_bounces` (given IDs are passed as `id` params, and no or empty IDs send `all=true`). Verify: `uv run pytest` passes.
- [ ] 3.7 Add `tests/test_registration.py`, asserting that `create_production_server()` exposes exactly 70 tools, including every tool named in the proposal. Verify: `uv run pytest` passes.
- [ ] 3.8 Run ruff, mypy, build and the whole suite. Verify: `uv run ruff check src/ && uv run mypy src/ && uv build && uv run pytest` all pass.
- [ ] 3.9 Update `CLAUDE.md`: the tool count, the `tests/` folder now existing with the command for running one test, and `json_data: Any` on `_request`. Verify: the documented `uv run pytest tests/test_templates.py::<name>` command runs.

## 4. Manual checks against a disposable Listmonk

- [ ] 4.1 Start a local Listmonk (`docker compose -f docs/listmonk-docker-compose.yml up -d`), create an API user and token, and point a local `.env` at `http://localhost:9000`. Verify: `curl -H "Authorization: token <user>:<token>" http://localhost:9000/api/health` returns `{"data":true}`. If Docker isn't available, mark section 4 as not run and say so. Do not use production.
- [ ] 4.2 Run the main scenario of each spec in `specs/` through the MCP server (`uv run listmonk-mcp`, with an MCP client or the inspector) against the local instance. Verify: each scenario's result is recorded as pass, or fail with a `NOTE:`.
- [ ] 4.3 Run only the read-only tools (`get_about_info`, `get_settings`, `get_logs`, `get_dashboard_counts`) against production. Verify: `get_about_info` returns the version and build, and the `get_settings` SMTP password is masked by Listmonk.

## 5. Publish to the fork

- [ ] 5.1 Push `master` to `origin` (`harberlaman/listmonk-mcp`) with no tags. Verify: `git status -sb` shows `master` level with `origin/master`, and `git ls-remote --tags origin` lists no new `v*` tag.
- [ ] 5.2 Collect every `NOTE:` that wasn't fixed (including `import_subscribers` repeating P3) into a short list at the end of this file, as input for the fix and guardrails changes. Verify: the list exists.

## Workflow follow-up

- Archive this change once sections 1 to 5 are done (`/opsx:archive`).
- Then propose the next change (fix core tools: P1, P3, P4, P5, P7 and the error mapper).
