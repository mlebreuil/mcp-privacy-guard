# Research: Pseudonymize Data Sent to the Model

**Feature**: `001-mcp-pseudonymization` (carried over from panos-mcp draft 002; to be revised by `/speckit-plan`) | **Date**: 2026-10-17

All Technical Context unknowns are resolved below. Items marked **Verify at implementation**
are facts about third-party software that may move and must be re-checked when the related
task starts.

---

## R1. Feasibility in Claude Code (the spec's main risk)

The spec needs two things the MCP server cannot do itself, because neither the user's question
nor the assistant's answer passes through it: rewrite the question before it is sent (FR-022)
and show answers with real values (FR-015).

- **Finding**: the Claude Code plugin ("mod") API of build 2.1.301 supports both. Source: the
  API declarations shipped with the `plugin-authoring` skill (`claude-code.d.ts`).
  - `on('prompt.submit', hook)`: "Rewrite with `next({ ...e, text })` (the user message on
    screen follows) or, in its place, stop it with `{ drop: reason }`." The rewritten text is
    what reaches the model.
  - `on('ui.render', { component: 'AssistantMessage' }, hook)`: "A rewrite changes the drawing
    and leaves the stored message alone." Same for `UserMessage` ("a rewritten `text` changes
    the row alone, never what the model read"), `ToolUse` and `ToolResult`.
  - Render hooks are "raised on every attached surface"; `e.surface` is `terminal`, `desktop`,
    `vscode` or `mobile`.
  - `on('tool.call', { tool }, hook)` (added for the generic design): `next({ ...e, input })`
    runs the tool with rewritten arguments; `await next(e)` resolves to the result, and
    returning `{ result }` hands the model a rewritten result instead (core validates it against
    the tool's output schema). `{ deny }` after the tool ran withholds its result: the model reads
    "`<tool>` ran, and a plugin withheld its result". A failing guard is skipped unless the
    registration carries `.catch(... { deny })`. This lets the guard handle any MCP server with
    no change to the server.
  - `$.process.run` runs a local command by argv; `$.ui.toast` / `$.ui.status` show short
    notices.
- **Caveat 1 (fail-open default)**: "a broken plugin never blocks" a prompt. A plugin whose
  hook throws lets the original prompt through. The hook MUST be wrapped with the documented
  `.catch(($, e, next) => next.called ? next(e) : { drop: "…" })` so a failure drops the
  prompt instead (FR-024). Contract test required.
- **Caveat 2 (slash commands)**: a rewrite of `text` is not applied when the submission runs a
  slash command (`e.command` set); the person is told. Skill/command arguments must be handled
  at `command.run` / `skill.prompt`. Decision: drop any slash-command submission whose
  arguments contain an identifying value, with a message asking to rephrase as a plain
  question. Plain slash commands without such values pass.
- **Caveat 3 (remote surfaces)**: `mobile` and remote `desktop` surfaces are drawn by a remote
  client, so a revealed tree would carry real values off the machine. Decision: reveal only
  when `e.surface === 'terminal'` or `'vscode'` (both local); other surfaces draw stand-ins.
  **Verify at implementation** whether `desktop` can be told apart as local.
- **Decision**: ship a small Claude Code plugin with the project (the "reveal companion"). It
  does three things: rewrite prompts, reveal rows on local surfaces, and guard tool calls (R9).
  All pseudonymization logic stays in Python and is reached through a local CLI (R6).
- **Fallback** (spec Assumptions): if a future build removes these APIs, the companion
  degrades to blocking prompts that contain identifying values, and the user can still run
  `panos-mcp pseudonym reveal`.
- **Verify at implementation**: event names and payloads against the build in use; pin a
  minimum Claude Code version in the plugin manifest.

## R2. Where pseudonymization happens in the server

- **Decision**: one choke point in `server.readonly_tool`. Before the tool runs, arguments are
  translated from stand-ins to real values (R5). After it runs, the `ToolResult`, or the
  `ToolErrorInfo` on failure, is pseudonymized as a typed model, and the summary is built
  from the pseudonymized model. The server instructions and the TLS warning are pseudonymized
  too. No tool handler changes.
- **Rationale**: every result already goes through this wrapper, so nothing can bypass it.
  Pseudonymizing typed models, not rendered JSON, lets each field be classified by meaning
  instead of guessing from text.
- **Alternatives considered**: post-processing the JSON text with regexes (cannot tell a rule
  name from an enum value, fails open); pseudonymizing in the parsers (would leak through
  error messages and summaries built elsewhere).

## R3. Classifying fields (fail closed)

- **Decision**: every `str` field (and `list[str]`) of the result models in `models/` carries
  a classification, as `Annotated[str, Pii(Kind.RULE_NAME)]` or `Annotated[str, Keep]`. The
  walker pseudonymizes by the annotation. Unannotated strings are treated as `TEXT`
  (whole-value stand-in, FR-007). A contract test walks every model reachable from every
  tool's return type and fails on any unannotated string field, so a new field cannot slip
  through silently.
- **Enum-typed fields, numbers, booleans, timestamps** pass unchanged (FR-003).
- **Keep values**: the existing `samples/sanitize/keeplist.py` `BUILTIN` set (PAN-OS
  built-ins, predefined applications and services) is moved to a shared module and used by
  both the sample sanitizer and the live pseudonymizer (FR-003). The operator keep list and
  hide list (FR-018) are added on top.
- **Kinds**: `IP` (address, prefix, range, wildcard), `FQDN`, `HOSTNAME`, `URL`, `EMAIL`,
  `MAC`, `SERIAL`, `USER`, `GROUP`, and one name kind per object type: `DEVICE_NAME`,
  `DEVICE_GROUP`, `TEMPLATE`, `TEMPLATE_STACK`, `RULE_NAME`, `ADDRESS`, `ADDRESS_GROUP`,
  `SERVICE`, `SERVICE_GROUP`, `APP_GROUP`, `TAG`, `ZONE`, `PROFILE_GROUP`, `INTERFACE`,
  `VSYS`. Plus `TEXT` (descriptions, free log fields) and `MIXED` (strings such as Panorama
  error text or dynamic-group filters, which are scanned for embedded values, then tokenised).

## R4. Stand-in formats

Constraints: same kind and shape (FR-005); consistent per user and secret (FR-004); different
real values give different stand-ins; unreadable without the secret (FR-006); fast at
10,000-rule scale (SC-006).

- **IP addresses: keyed, prefix-preserving permutation** (the Crypto-PAn construction, with
  HMAC-SHA256 as the pseudo-random function instead of AES, so no new dependency). It is a
  bijection, so it can be inverted with the key and needs no table, and it preserves the
  length of every shared prefix. That keeps any subnet containment and range order the model
  needs. Address class is preserved by fixing the bits of the containing special block:
  `10/8`, `172.16/12`, `192.168/16`, `100.64/10`, `127/8`, `169.254/16`, multicast,
  broadcast, the documentation ranges, `fc00::/7`, `fe80::/10`. Public IPv4 addresses keep
  their first octet and IPv6 global addresses keep their first 16 bits, so they stay public.
  That reveals the /8 (/16 for IPv6) of public addresses, which identifies a registry
  allocation, not an organisation. This residual is accepted and documented. Masks
  (`255.255.255.0`), `any` and `0.0.0.0/0` pass unchanged.
- **Ambiguity**: a stand-in IP may equal some other real IP of the estate (unavoidable for a
  bijection). This is harmless because the model only ever sees stand-ins (FR-001, FR-022), so
  every IP coming back from the model is a stand-in and is inverted. See R5.
- **Names**: `<prefix>-<base32(HMAC(key, kind ‖ real))[:6]>`, lower case. Examples: `rule-k3f9qa`,
  `addr-…`, `grp-…`, `svc-…`, `svcg-…`, `appg-…`, `tag-…`, `zone-…`, `dg-…`, `tpl-…`,
  `stk-…`, `fw-…`, `prof-…`, `if-…`. The prefix tells the model the object type (it would
  infer it anyway). A collision within a kind extends the suffix by two characters. Stand-ins
  are valid PAN-OS names. A reverse table is required (R7).
- **FQDN / hostname**: each label below the public suffix is replaced, keyed by its full
  parent chain (`app.corp.example.com` → `h-9x2.d-k7q.example.com`… with `example` itself
  replaced: `h-9x2.d-k7q.d-p1m.com`). Labels sharing a parent stay sharing it (FR-005). The
  TLD is kept.
- **URL**: scheme kept, host as FQDN, path and query replaced by `/p-<token>`.
- **Email**: `u-<token>@<fqdn stand-in>`. **User**: `DOMAIN\user` → `dom-<t>\u-<t>`;
  `user@realm` like email.
- **MAC**: locally-administered prefix `02:` plus keyed bytes (hides vendor OUI).
- **Serial**: 12 digits starting `99`, keyed; collisions extend the attempt counter (as in
  `Forger._mapped`).
- **TEXT**: `text-<token>`. The model learns only that a description exists and whether two
  descriptions are equal. **MIXED**: embedded IPs, FQDNs, emails and known names are replaced
  in place, and everything else is kept only if it is built-in vocabulary. Otherwise the whole
  value becomes `text-<token>`.
- **Alternatives considered**: reuse the sample `Forger` octet scheme as is (keeps /8, /16 and
  /24 containment only, so a `/20` or `/27` would break SC-002); format-preserving encryption
  (FF3-1) for names (needs a new dependency and still needs a name alphabet; reversibility
  without a table is not needed for names since a table is kept anyway); random tokens
  without a key (not consistent across restarts).

## R5. Translating tool arguments

- **Decision**: the wrapper walks the tool's keyword arguments by their declared input types,
  which are annotated like the models. IP-typed arguments, and IPs inside filters, are
  always inverted. Name-typed arguments are looked up in the reverse table; an unknown token
  is passed through as a literal (FR-010), so Panorama answers "not found". The not-found
  error and any "did you mean" suggestions are pseudonymized like any output. Log filter
  strings are parsed by the existing log-filter builder, values are translated, and the
  filter is rebuilt. Validation, `xpath_literal` and the allow-list then run on the real values
  unchanged (FR-011).
- **Spec impact (FR-009)**: since the user's question is pseudonymized (FR-022), real values
  can no longer reach the model, and an IP argument cannot be both a stand-in and a real value.
  Proposal: FR-009 becomes "a name argument that is not a known stand-in is used as typed",
  and IP arguments are always read as stand-ins. **The spec has been updated accordingly**
  (FR-009, Story 2 scenario 2).

## R6. Python side of the companion: CLI, not a second server

- **Decision**: a new CLI group `panos-mcp pseudonym` (same package, same store) that the
  plugin calls through `$.process.run`, JSON on stdin and stdout:
  - `pseudonym prompt`: pseudonymize a question (shape detection plus the name dictionary,
    R8). Returns the text, the replacements made and the warnings. Exit code ≠ 0 means the
    plugin drops the prompt.
  - `pseudonym table --since <rev>`: the stand-in → real entries added since a revision, for
    the plugin's in-memory reveal table.
  - `pseudonym reveal`: reveal a text (manual fallback; also used by tests).
  - `pseudonym status`: secret present and readable, store revision, categories covered.
- **Rationale**: keeps the TypeScript shim free of cryptography and classification, and
  keeps one implementation tested by the existing Python suite. No network listener
  (constitution). The cost is about 0.2–0.4 s of Python start-up per prompt, which is
  acceptable. Reveal does not use the process, so rendering stays instant (SC-005).
- **Alternatives considered**: the plugin reading the store directly (duplicates logic in
  TypeScript); a long-lived helper over stdio (more moving parts, needed only if start-up
  latency proves a problem: **verify at implementation**); an MCP tool for reveal (the model
  would see its output, so rejected).

## R7. The store: secret and mapping record

- **Decision**: directory `~/.config/panos-mcp/pseudonym/` (overridable with
  `PANOS_MCP_PSEUDONYM_DIR`). Its key is separate from the sample-sanitizer key, so sample
  data and live data never share stand-ins. It holds:
  - `secret.key`: 32 random bytes, created on first start with mode `0600` in a `0700`
    directory. If the file exists but cannot be read, or its permissions are broader than the
    owner's, the server refuses to serve data (FR-013).
  - `mapping.sqlite` (stdlib `sqlite3`, WAL mode, `0600`): table
    `standin(kind, standin, real, first_seen, rev)` with unique indexes on `(kind, real)` and
    `standin`, plus table `names(kind, real)`, the name dictionary for prompts (R8). It is
    written by the server and read and written by the CLI. Concurrent access between two
    processes is handled by SQLite.
- The directory is refused if it lies inside a git work tree that does not ignore it (reuse
  `_git_tracks`).
- **Logging**: the store never logs values. The log redaction filter gains a rule for
  stand-in pairs (FR-014).
- **Rotation / loss** (spec edge case): a new secret starts a new store. Stand-ins of the old
  one are reported as "unknown stand-in (issued with another secret)" by reveal, never
  guessed.

## R8. Recognising identifying values in questions (FR-023)

- **Shapes**: IPv4/IPv6 addresses, prefixes and ranges; FQDNs (with a public-suffix check
  against a small bundled list); e-mail; MAC; 12-digit serials; `DOMAIN\user`. Each is
  replaced with the same function as tool output, so the stand-ins match (SC-008).
- **Names**: whole-token, case-sensitive match against the name dictionary in the store. The
  server fills the dictionary:
  1. from every result it pseudonymizes;
  2. by a background warm-up at start-up that reads the device, device-group, template, tag,
     zone, rule and object names of the configuration through the existing cached, read-only
     service calls, with bounded concurrency. The prompt CLI never contacts Panorama.
- **Common words** (spec edge case): a name that is also in a bundled common-word list (about
  5,000 English words plus networking terms such as `inside`, `outside`, `trust`, `dmz`,
  `web`, `test`) is replaced only when quoted, back-ticked, or preceded within three tokens by
  a cue word (`rule`, `object`, `group`, `zone`, `tag`, `device group`, `template`,
  `firewall`, `address`, `service`). The user sees every replacement (FR-025), so a missed or
  over-eager match is visible.
- **Before the warm-up completes**, names not yet seen are not recognised. `pseudonym status`
  reports the warm-up state, and the plugin shows "name list still loading" in the status line
  until it is complete. **Residual risk**: a rule name typed before the warm-up ends reaches
  the model. Documented.

## R9. Other ways real data could reach the model in Claude Code

- **The model reading the store or calling the CLI**: with its own `Bash`, `Read` or `Grep`
  tools the model could run `panos-mcp pseudonym table` or read `mapping.sqlite`. Decision:
  the plugin's `tool.call` guard denies any built-in tool call whose input names the store
  directory, `panos-mcp pseudonym`, or the server's configuration file. It is best effort
  (spellings vary), so the documentation also gives Claude Code permission `deny` rules for
  the same paths and commands as defence in depth.
- **Pre-existing, out of scope but documented**: the model reading the Panorama API key from
  the MCP client configuration and querying Panorama directly through `Bash`. The same deny
  rules cover the config file.
- **Files and pastes** (spec Assumptions): out of scope.
- **Compaction summaries, titles, prompt suggestions**: these are generated by the model from
  the stand-in transcript, so they contain stand-ins only. They are revealed on display when
  drawn as `AssistantMessage`.
- **Transcript on disk**: holds stand-ins (rewrites happen before storing), so `--resume`
  works and reveals again.

## R10. Plugin implementation language versus the constitution

- **Finding**: Claude Code plugins are TypeScript modules (`hooks/register.ts`). The
  constitution says: "Introducing another language for runtime code requires a MAJOR
  amendment."
- **Decision**: propose constitution **v2.0.0**. Runtime code stays Python, with one
  exception: a client-integration shim may be written in the language its host client
  requires, if it holds no pseudonymization, classification or Panorama logic, delegates to
  the Python CLI, and is tested with the host's own test runner. The amendment is a
  prerequisite task, before any plugin code.
- **Alternative considered**: Claude Code "classic" shell hooks in Python
  (`UserPromptSubmit`). They can block or add context but cannot rewrite the prompt or the
  display, so they fail FR-015 and FR-022. Rejected.

## R11. Testing

- **Python** (offline, as today):
  - Unit tests: stand-in formats, prefix preservation (property tests over random networks),
    inversion, collisions, store permissions and refusal, prompt recognition, common-word
    rule.
  - Contract tests:
    - every tool returns no real value (SC-001), using the values found in the sample
      library as "real";
    - every result-model string field is classified (R3);
    - tool names and schemas are unchanged (snapshot);
    - arguments round-trip (SC-003);
    - errors are pseudonymized.
  - Benchmark: the large estate with pseudonymization on stays under 5 s (SC-006).
- **Plugin**: `claude plugin validate` and `claude plugin test` with `*.test.ts`:
  - a prompt is rewritten;
  - a CLI failure drops the prompt (Caveat 1);
  - a slash command carrying values is dropped;
  - reveal on `terminal`, none on `mobile`;
  - unknown stand-ins are marked;
  - the guard denies reads of the store.

  These need the `claude` CLI. They are a local gate and a CI job that is skipped when the
  CLI is absent. **Verify at implementation** whether CI can install it.
- **End to end**: a quickstart scenario with the offline demo (`PANOS_MCP_SAMPLES_SCENARIO`)
  and the plugin loaded through `--plugin-dir` (see [quickstart.md](./quickstart.md)).

## R12. Offline demo and samples

- Pseudonymization is always on (FR-017), including with `PANOS_MCP_SAMPLES_SCENARIO`. The
  demo uses a throwaway store under the scenario's temp directory unless
  `PANOS_MCP_PSEUDONYM_DIR` is set, so demos do not fill the user's real store.
- Tests use an ephemeral in-memory store with a fixed test key, like
  `MappingStore.ephemeral`.
