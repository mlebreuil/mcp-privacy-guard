# mcp-privacy-guard Constitution

## Core Principles

### I. No Real Data Reaches the Model (NON-NEGOTIABLE)

- Every identifying value in a protected MCP server's results, error messages and the
  user's questions MUST be replaced by its stand-in before it leaves the user's machine.
- The guard MUST fail closed. A value whose kind cannot be determined is treated as
  identifying. A result that cannot be processed (error, timeout, unsupported or binary
  content, too large to finish in time) is withheld from the model, never passed through.
  A question that cannot be checked is not sent.
- Every hook that can let data through on failure MUST be wrapped so that failure blocks
  instead. Host defaults that fail open (for example "a broken plugin never blocks") MUST be
  overridden explicitly and covered by a test.
- The categories of identifying values required by company policy (spec FR-004) are a floor.
  No profile, setting or keep list may remove a category for fields of that kind.

Rationale: this is the compliance requirement the project exists for. One leak is a policy
breach, so wrongly hiding a value is always better than wrongly passing it.

### II. Local Only, Self-Protecting

- The pseudonymization secret, the mapping record and revealed text MUST stay on the user's
  machine, in files readable only by the user. They MUST NOT be logged, sent over the network,
  stored in the conversation the model reads, or kept in host-synced plugin storage.
- The engine MUST NOT open a network listener and MUST NOT contact the MCP servers' data
  sources itself.
- Reveal MUST happen only on surfaces drawn locally. Remote or mobile surfaces show stand-ins.
- The guard MUST stop the model's own tools from reading the secret or the mapping and from
  running reveal or table commands, and the documentation MUST give matching host permission
  deny rules as a second layer of defence.
- Errors, logs and status output MUST NOT contain real values or stand-in/real pairs.

Rationale: only the user's machine is trusted. The model provider, the network path and
remote clients are not.

### III. Server-Agnostic by Construction

- The guard MUST work with any MCP server, current or future, without changes to the servers
  or to the MCP configuration.
- Every MCP server is protected by default, the moment it is added. Only an explicit operator
  exemption by server name removes protection.
- Server-specific knowledge belongs in profiles that ship as data, never in engine code paths
  that only run for one server. A missing or invalid profile falls back to the default
  profile, with a notice. It never falls back to pass-through.
- A profile can only make handling more precise. It cannot weaken Principle I.

Rationale: protection that depends on each server's cooperation fails for the next server
someone adds.

### IV. Consistent, Shape-Preserving, Keyed Stand-ins

- Within one session, the same real value MUST always get the same stand-in, across tools,
  servers and turns. Different real values MUST get different stand-ins.
- Stand-ins MUST be valid only in the session that issued them. Each session uses its own
  secret. The secret and the mapping are deleted when the session ends, and no record that
  links a stand-in to a real value persists beyond it. A stand-in from an ended session MUST
  never be translated or revealed, in any session.
- Stand-ins MUST keep the kind and the relationships the model needs: subnet containment,
  range order and address class for IPs, shared parent domains for FQDNs, and the domain part
  of user names.
- Name stand-ins MUST use one reserved, recognisable form that does not depend on the object
  type, the field or the server. One real name has exactly one stand-in everywhere, so the
  model can correlate it across configuration, logs and servers by plain string equality. The
  model infers the object type from context.
- Stand-ins MUST come from a keyed cryptographic construction over the per-session secret. Anyone
  holding only stand-ins, or a list of candidate real values, MUST NOT be able to recover real
  values without the secret.
- Values coming back from the model are always read as stand-ins. Reveal and argument
  translation replace only stand-ins they know. Unknown ones are left as they are and marked,
  never guessed, and translation never discloses other mappings.

Rationale: consistency within a session makes multi-step debugging possible, keeping shape
keeps answers correct, and keying keeps the scheme safe against dictionary attacks.
Session-only stand-ins mean that nothing leaving the machine can be linked to real values,
or to another session's stand-ins, once the session is over. A type-specific name
form would give the same real name different stand-ins wherever its type is known differently
(or not at all), and the model would lose the link between them.

### V. One Engine, Thin Client Shims

- All pseudonymization, classification, translation, reveal-table and store logic MUST live
  in a single core engine written in Python, with the standard library preferred and each
  third-party runtime dependency justified in the plan.
- A client integration (for example the Claude Code plugin) MAY be written in the language its
  host requires, only if it holds no cryptography, classification or mapping logic. It hands
  every decision to the engine through a local, documented interface (CLI, JSON over
  stdin/stdout) and is tested with the host's own test runner.
- Engine interfaces MUST define their exit codes and error shapes, and MUST NOT provide any
  disable or pass-through mode.
- Adding another language for engine code, or moving logic into a shim, requires a MAJOR
  amendment.

Rationale: if the logic were written twice, the two copies could drift and leak where they
differ. One tested engine is the one place to audit.

### VI. Test-First with Leak Tests as the Gate (NON-NEGOTIABLE)

- Tests MUST be written and seen failing before the code that makes them pass.
- The test suite MUST run offline, with no real infrastructure, using an ephemeral store and a
  fixed test key. The `panos-mcp` offline demo mode and a generic test MCP server are the
  reference environments.
- Required gates before merge:
  - **Leak tests**: for every tool of every reference server and for a question test set, no
    known real value appears in what the model receives.
  - **Fail-closed tests**: each failure path (engine error, timeout, unreadable secret,
    invalid profile, unsupported content, shim exception) withholds or blocks.
  - **Consistency and structure tests**: determinism within a session, unrelated stand-ins
    across sessions, deletion of the session secret and mapping at session end, no collisions,
    property tests for prefix and range preservation, and argument round-trips.
  - **Reveal tests**: only known stand-ins are revealed, unknown ones are marked, and nothing
    is revealed on remote surfaces.
- Performance budgets in the spec (for example under 1 s added per tool call and per question)
  MUST have a benchmark test.

Rationale: privacy claims that are not tested cannot be relied on. Leak tests are how this
project shows it is compliant.

### VII. Transparent Scope, No Off-Switch, Simplicity

- Pseudonymization MUST always be on for protected servers and questions. There MUST be no
  global disable setting, flag or environment variable.
- At session start the guard MUST report that it is active, which servers are protected or
  exempt, and the profile of each. It MUST tell the model that the values it sees are
  stand-ins.
- The documentation MUST state what leaves the machine and in what form, and what is not
  covered (built-in tool output, pasted files, attachments, other clients, an uninstalled
  guard). A compliance reviewer must be able to check this from the documentation alone.
- Start with the simplest design that meets the spec (YAGNI). Extra complexity (long-lived
  helpers, caches, more languages, new dependencies) MUST be justified in the plan's
  Complexity Tracking with a measured need.

Rationale: an auditor can only trust a guard if they can see what it covers, see that it
cannot be switched off, and read how it works.

## Security & Data Handling Constraints

- The session secret and mapping are created owner-only (file `0600`, directory `0700`) when
  the session starts, and deleted when it ends. If their permissions are broader, or they
  are missing or unreadable during the session, the guard refuses to process questions and
  protected results. It never silently creates a new secret mid-session.
- The store directory MUST NOT lie inside a version-controlled tree that does not ignore it.
- A conversation that carries stand-ins from an ended session (for example, a resumed one)
  is blocked until a new conversation starts. Its stand-ins are never revealed wrongly or
  translated with another session's secret.
- Real data MUST NOT be committed to the repository. Test fixtures and samples use synthetic
  or sanitized data.
- Third-party host APIs this project relies on (Claude Code plugin events and payloads) MUST
  have a pinned minimum host version, checked at start-up. An unsupported host blocks
  questions (fail closed), and a contract test covers this.
- Any change that widens what can reach the model or leave the machine needs a security
  review recorded in the pull request.

## Development Workflow & Quality Gates

- Features follow the Spec Kit flow: specify → clarify (as needed) → plan → tasks →
  implement. Each plan MUST include a Constitution Check against Principles I–VII and record
  any justified deviation in Complexity Tracking.
- Every pull request MUST pass the engine test suite, the shim tests (when the host CLI is
  available; skipping them in CI MUST be visible in the job output), linting and type checks.
  Reviewers MUST confirm that no gate in Principle VI was weakened.
- Changes to stand-in formats, the store schema, or engine interface exit codes and payloads
  are breaking. They need a migration note and a version bump of the affected component.
- Facts about third-party software noted as "verify at implementation" in research MUST be
  re-checked when the related task starts, and the result recorded.

## Governance

- This constitution supersedes other project practices. Where a spec, plan or task conflicts
  with it, the constitution wins until it is amended.
- Amendments are made by pull request that updates this file, includes a Sync Impact Report,
  and states the version bump and its reason. Amendments that weaken Principle I, II or VI
  need the explicit approval of the project owner and a note on the compliance impact.
- Versioning follows semantic versioning:
  - MAJOR: a principle is removed or redefined in a backward-incompatible way, or a
    non-negotiable rule is relaxed.
  - MINOR: a principle or section is added, or guidance is materially expanded.
  - PATCH: clarifications and wording changes with no change in meaning.
- Compliance is reviewed at every plan (Constitution Check), at every pull request review, and
  in `/speckit-analyze` runs. A violation is a blocking finding.
- Runtime development guidance for agents lives in `CLAUDE.md` (once created) and MUST NOT
  contradict this document.

**Version**: 2.0.0 | **Ratified**: 2026-10-18 | **Last Amended**: 2026-10-19
