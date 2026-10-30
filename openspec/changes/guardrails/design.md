# Design

## Context

See proposal.md for the motivation. The constraints that shape the approach:

- All 70 tools register at import on one module-level `mcp = FastMCP(...)`, through `@mcp.tool()` (`server.py:118`). Config is loaded only inside `lifespan`, which runs after `mcp.run()` has started.
- `mcp` 1.11.0's FastMCP has no `remove_tool`. Its low-level handlers are bound to `self.list_tools` and `self.call_tool` (`fastmcp/server.py:232-236`), so a subclass can override both.
- Tests depend on the module-level `mcp`:
  - `server.mcp._tool_manager.get_tool(name)` reads descriptions, including those of gated tools (`test_admin.py:70`, `test_bounces.py:27,54`).
  - `create_production_server()` is called repeatedly in one process (`test_mcp_interface.py`, `test_registration.py`).
  - `create_production_server()` has to work in a clean interpreter with no `LISTMONK_MCP_*` variables (`test_mcp_interface.py:115`).
- Listmonk v6.2.0 facts verified at the tag:
  - It masks 12 secret fields with one bullet per character (`cmd/settings.go:66-82`).
  - Settings keys are flat dotted names at the top level (`"bounce.sendgrid_key"`, `"bounce.forwardemail": {"key": …}`) (`models/settings.go`).
  - `/api/logs` returns `data: [...]` from a 5000-line buffer, oldest first (`cmd/main.go:77`, `internal/buflog/buflog.go:30-41`).

## Goals / Non-Goals

**Goals:**
- One place decides what is exposed, and it is reset completely on every `create_production_server()` call, so tests can't leak state into each other.
- The gate only hides tools. The 12 tool functions and their docstrings stay exactly as they are today.

**Non-Goals:**
- Per-tool flags, or allowing dangerous tools per client or per call.
- Masking anything other than `get_settings` output.

## Decisions

### D1. Hide gated tools in a FastMCP subclass, not by unregistering them

`mcp` becomes an instance of a small subclass, `GuardedFastMCP(FastMCP)`, with a `hidden_tools: frozenset[str]` attribute. It overrides two methods:
- `list_tools()` calls `super()` and filters out names in `hidden_tools`.
- `call_tool(name, …)` raises `ToolError(f"Unknown tool: {name}")` for a hidden name, which is FastMCP's own unknown-tool error, before anything runs. Otherwise it calls `super()`.

`create_production_server(allow_dangerous: bool = False)` sets `mcp.hidden_tools` to either an empty set or `DANGEROUS_TOOLS`, logs the INFO line, and returns `mcp`.

Alternatives considered:
- **Register gated tools only when allowed** (a `@dangerous_tool` decorator that collects functions, plus `mcp.add_tool` in `create_production_server`). Once added, a tool can't be removed, so a test that builds the server with the flag on leaves the tools registered for every later test. `test_admin.py` and `test_bounces.py` would also lose access to the gated tools' descriptions.
- **Delete them from `mcp._tool_manager._tools`.** This writes into FastMCP's private state, can't be undone in the same process, and breaks those same tests.

To clients the two are indistinguishable: a hidden tool isn't listed, and calling it gives the same "Unknown tool" error as a name that never existed. That's why the specs say "exposed" and not "registered".

### D2. The list is a named constant, checked against the registry

`DANGEROUS_TOOLS: frozenset[str]` sits next to `create_production_server`, with the 12 names. `create_production_server` asserts that every name is in `mcp._tool_manager`'s tools (one read of private state, the one place D1's tests already use). A typo or a rename therefore fails at startup and doesn't silently expose a tool. A test pins the set's exact contents.

Alternative: a marker attribute on each function. That spreads the list over 2.5k lines, and you can't review it at a glance.

### D3. Read the flag in `run()` before starting the server, and reuse that config in the lifespan

- `config.py` gains `allow_dangerous: bool = Field(default=False, …)`. Pydantic parses `true/false/1/0/yes/no/on/off` and rejects anything else, so an invalid value is a startup error, as the spec requires.
- `run()` calls `load_config()` and `validate_config()`, then `create_production_server(allow_dangerous=config.allow_dangerous)`, then `server.run()`.
- `lifespan` uses the module `_config` when it is already set and loads it only when it isn't. That keeps in-memory test sessions, which never call `run()`, working.
- Called with no argument, `create_production_server()` keeps the safe default (`False`) and needs no environment, so the clean-interpreter test still passes.

Alternative: load config inside `create_production_server()`. That breaks the clean-interpreter test, and it makes building the server depend on the environment.

### D4. Masking is a pure function in its own module

A new `masking.py` holds `mask_settings(data: Any) -> Any`, which returns a masked deep copy:
- a dict value is masked when `re.search("password|secret", key, re.I)` matches, or when `(parent_key, key)` is `(None, "bounce.sendgrid_key")`, `("bounce.forwardemail", "key")` or `("bounce.lettermint", "key")`
- masking applies only to non-empty strings, which become `"********"`. Any other value (empty string, None, number) is returned unchanged.
- it recurses into dicts and lists. A list item inherits the parent key of its list, so `smtp[0].password` is matched by its own key name.

`get_settings` applies it to `result["data"]` and keeps its current output format. The module is named `masking`, not `secrets`, so it isn't confused with the stdlib module. `get_settings`'s docstring is updated: values are masked as `********`, and the output must never be written back.

Alternative: a hard-coded list of the 12 paths only. It misses any secret a later Listmonk version adds. Matching the name catches those, and the three explicit paths cover the `*_key` names, which a `key` pattern would get wrong (it would hide `aws_access_key_id` and the hCaptcha site key).

### D5. `get_logs(lines)` slices on the server

`lines: int = 100` is validated as 1 to 5000 with `ValidationError` before the request. The tool keeps the last `lines` items of `data`, in order, and returns `"Logs: last {shown} of {total} lines"` followed by one entry per line. If `data` isn't a list, it is treated as empty and the header says `0 of 0`, not crashing. The 5000 cap matches Listmonk's buffer size.

### D6. Split `delete_bounces` at the client too

- `client.delete_bounces(bounce_ids: list[int])` requires a non-empty list. The `all=true` fallback moves to a new `client.delete_all_bounces()`.
- The `delete_bounces` tool raises `ValidationError` for `None` or `[]`, so a bug in a later caller can't reach "delete all" by accident.
- The new `delete_all_bounces` tool calls `client.delete_all_bounces()` and is in `DANGEROUS_TOOLS`.
- `bounce_ids` becomes a required `list[int]` on the tool. A missing argument and an empty list both produce a tool error, so the spec holds either way.

### D7. Lock in "no arguments in the server log" with a test, don't add a filter

`run_tool` already logs only the tool name, the error type and the message (`exceptions.py:351-361`), and `client._request` doesn't log. A test calls a tool with a known secret argument, makes it fail through both the Listmonk-error path and the unexpected-exception path, and asserts with `caplog` that the secret appears in no record. `logger.exception` in the unexpected-exception path includes the traceback, which can contain local variable *names* but not their values: Python tracebacks don't print locals. The test covers this case.

## Risks / Trade-offs

- [The subclass overrides public FastMCP methods that a future `mcp` release could rename or bind differently] → `mcp` is pinned by the lockfile. The tests (spec scenarios "Flag unset", "Calling a gated tool while the flag is off") go through a real in-memory client session, so a change in binding breaks them visibly.
- [A hidden tool still exists in-process, so code inside the server could call it] → Only the MCP protocol path is a trust boundary here, and both list and call are filtered there. The tool functions are never called internally.
- [A new dangerous tool added later is exposed by default unless someone adds it to `DANGEROUS_TOOLS`] → `CLAUDE.md`'s "Adding an endpoint" convention gets a line about deciding whether the tool belongs in `DANGEROUS_TOOLS`. The registration test pins both counts, so adding any tool forces a look.
- [Over-masking `bounce.azure.shared_secret_header`, a header name] → Accepted. It's harmless, and an exception list would be worse to maintain.
- [`--config` is still ignored, so the flag can't be set from a `--config` file] → Same as every other setting today. Out of scope (proposal).
- [**BREAKING** for clients that used the 12 tools or `delete_bounces([])`] → Recorded in the CHANGELOG. The deploy change checks the it-ops plugin for references.

## Migration Plan

- Merged to `master` with no tag, like the earlier changes. The deployed image is still upstream until the deploy change.
- To get the old behavior in a deployment: `LISTMONK_MCP_ALLOW_DANGEROUS=true` in the compose env. The default deploy leaves it unset.
- Rollback: revert the merge commit. There is no data or settings migration.
