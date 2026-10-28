# Design

## Context

- `master` on `harberlaman/listmonk-mcp` is upstream `3e1cf0d` plus one local commit (`f1c9a0e`, which ignores `openspec/`). Work is committed directly to `master`, with no PRs (see proposal.md).
- The PR heads are fetched locally as `refs/upstream-pr/8` and `refs/upstream-pr/11`. Both branch from `3e1cf0d`. A test merge (`git merge-tree`) of #8 and #11 has no conflicts.
- #11 changes `update_template` in `client.py` and `server.py` only. #8 is almost entirely additive. Its only edit to existing code is loosening `ListmonkClient._request(json_data=...)` from `dict[str, Any] | None` to `Any`, needed because `update_setting` sends raw JSON values. It also bumps `pyproject.toml` to 0.2.0 and touches `uv.lock` and `README.md`.
- There are no tests (`tests/` doesn't exist). The only automated checks are ruff, mypy (strict) and `uv build`.
- Production Listmonk must not receive writes or sends during this change. Deployment details are in `openspec/HANDOFF.md`, which is not committed.
- `publish.yml` publishes to PyPI on any `v*` tag push.

## Goals / Non-Goals

**Goals:**
- Land #11 and #8 on `master` with their authorship and the link to upstream preserved.
- Leave `master` passing ruff, mypy and build, plus a small test suite covering the merged behavior most likely to be wrong.
- Check the specs' scenarios against a disposable Listmonk, not production.

**Non-Goals:**
- Changing #8's tool behavior: its "Successfully …" strings, missing secret masking, or the server-side `file_path` in `import_subscribers`. These belong to the fix and guardrails changes.
- Fixing the resource-copying gap or how errors are reported.
- Tagging, releasing or deploying.

## Decisions

### D1. Real merge commits of the PR heads, #11 first
`git merge --no-ff refs/upstream-pr/11`, then `git merge --no-ff refs/upstream-pr/8`, each with a message naming the upstream PR.
- *Why:* this keeps the original authors' commits, makes `git log` show exactly what came from upstream, and lets git recognise the commits if upstream ever merges these PRs.
- *#11 first:* it's small and independently correct, so #8's review starts from a `master` where `update_template` already carries the subject forward.
- *Alternatives:* squash merges or cherry-picks lose authorship and the link to upstream. Applying the diffs by hand loses both and risks transcription errors.

### D2. Review #8 before merging, using a checklist rather than a full rewrite
Read #8's diff for:
- every new endpoint's HTTP method and path against the Listmonk v6 API docs
- `test_campaign`'s payload, which must carry the whole campaign
- `update_setting` sending the raw value
- `delete_bounces` treating a missing or empty ID list as "all"
- `import_subscribers`' separate `AsyncClient`, which builds its own auth header

Record findings as `NOTE:` lines in tasks.md. Fix only what blocks merging, meaning a build/lint/type failure or a wrong endpoint. Defer everything else to the fix change.
- *Why:* it's 1,200 lines of AI-written code. A focused checklist catches the expensive mistakes without turning this change into a rewrite.

### D3. A small pytest + pytest-httpx suite, not full coverage
Add `tests/` with mocked-HTTP tests for:
1. the `update_template` subject carry-forward (all three scenarios)
2. the `update_setting` raw-JSON body
3. the `test_campaign` full payload
4. the `delete_bounces` all versus specific IDs
5. a check that the production server (`create_production_server()`) exposes 70 tools

Everything else is checked by hand against a disposable Listmonk (D4).
- *Why:* these are the places where the merged code could be silently wrong. The tool-count check also catches #8 tools that fail to register on the production server, which is the same kind of copying gap as the resources issue.
- *Alternative:* one test per tool, which is about 41 tests for behavior we didn't write. It isn't worth it before the fix change reshapes the return values.
- The dev dependencies (`pytest`, `pytest-asyncio`, `pytest-httpx`, `pytest-mock`) are already declared, so nothing is added to `pyproject.toml`.

### D4. A disposable local Listmonk for manual checks
Run `docker compose -f docs/listmonk-docker-compose.yml up -d` on a dev machine, create an API user, and point `.env` at `http://localhost:9000`.
- Read-only tools (`get_about_info`, `get_settings`, `get_logs`, `get_dashboard_*`) may also be run against production to confirm the response shapes.
- Nothing that writes, deletes or sends runs against production.

### D5. Push `master`, never push tags in this change
After verification, `git push origin master`. No `v*` tag, because that would trigger the PyPI publish of a package name owned by upstream. The deploy change decides tag naming and the publish workflow.

## Risks / Trade-offs

- [The merge has no conflicts but is wrong where #8 and #11 meet in `update_template`] → read the merged function after D1, and the D3 carry-forward tests run against the merged code.
- [#8 endpoints are wrong for Listmonk v6.2.0] → the D2 checklist plus D4 manual checks. If a tool is broken but the build is fine, record it as `NOTE:` rather than fixing it here.
- [`json_data: Any` weakens type checking for every request] → accept for now. It's the smallest change that lets `update_setting` send raw values.
- [Destructive tools land on `master` with no gate] → `master` isn't deployed. The deployed image clones upstream until the deploy change pins a tag, and the guardrails change must be done before that.
- [`import_subscribers` repeats the P3 problem (a path on the server, and a `TypeError` on a missing file through the `status_code=None` mapper)] → not fixed here. Record it as input to the fix change.
- [Running a local Listmonk needs Docker on the dev machine] → if it isn't available, record the D4 checks as not done instead of running them against production.
