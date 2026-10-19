# Feature Specification: Pseudonymize MCP Data Sent to the Model

**Feature Branch**: `001-mcp-pseudonymization`

**Created**: 2026-10-17

**Status**: Draft

**Input**: User description: "the current implementation of the mcp server will hand over data, either firewall configuration and logs, to the model. The company polics prohibit this. The goal of this new feature would be to anonymise the data handed hover to the model still keeping these consistent (the same data anonimize the same way) and being able to recontruct the real data on the user's machine before display."
Refined: "Could the anonymization plugin be the same whatever the MCP server used behind? That is, generalise the plugin and leave the current MCP configuration untouched." → separate repository, no pseudonymization inside the MCP servers.

## Context

Engineers debug with an AI assistant (Claude Code) connected to MCP servers that read
infrastructure data: today `panos-mcp` (Panorama firewall configuration and logs), later
others. Every tool result is sent unchanged to the model provider, and so is every question
the engineer types. Company policy prohibits sending this data.

**mcp-privacy-guard** sits inside Claude Code, between the engineer, the MCP servers and the
model. It:

- replaces identifying values with consistent stand-ins before anything reaches the model;
- turns stand-ins in the model's tool calls back into real values before the MCP server
  receives them;
- shows the engineer the real values on their own screen.

The MCP servers and the MCP configuration are not changed. Any MCP server, current or future,
is covered.

Terms used in this spec:

- **Pseudonymize**: replace a real value with a stand-in that looks like the same kind of value
  (an IP stays an IP, a name stays a name) and is always the same for the same real value.
- **Reveal**: turn stand-ins back into the real values, locally, for the user.
- **Protected server**: an MCP server whose tool calls the guard handles. By default every MCP
  server is protected.
- **Profile**: a description of one MCP server's data: which fields hold which kind of value,
  and which values are safe to keep. It makes pseudonymization precise for that server.

## Clarifications

### Session 2026-10-18

- Q: Where must real values be shown automatically, given that this Claude Code version can
  only rewrite what's displayed in the terminal CLI, not in the VS Code extension or the
  desktop app? → A: Terminal CLI only. The guard refuses to run in the VS Code extension and
  the desktop app (it blocks questions and withholds protected results there), so users never
  work with stand-ins they cannot read.
- Q: Should text the user pastes into a question be pseudonymized like typed text? → A: Yes,
  pasted text is covered exactly like typed text. Images, attached files and documents stay
  out of scope.
- Q: When a question carries an image, file or document attachment, should the guard let the
  attachment through unprotected, or block the question? → A: Block any question that carries
  an attachment, and tell the user to paste the text instead.
- Q: Should the guard require Claude Code's sandbox (with reads of its folder denied) and refuse
  to run without it? → A: Yes. Without the sandbox the guard blocks questions and withholds
  protected results, and says how to enable it.
- Q: Should name stand-ins carry a prefix showing their kind (`fw-…`, `rule-…`), which could
  differ between servers and fields? → A: No. Every name uses one generic form (`n-…`) and is
  identical everywhere, so correlation across logs, configuration and servers is exact; the
  model infers the kind from context.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use any MCP server without sending real data to the model (Priority: P1)

An engineer asks "which rules allow traffic to the web servers?". The assistant calls a
`panos-mcp` tool. Before the result reaches the model, the guard replaces every identifying
value with its stand-in. The model provider receives no real hostname, IP address, serial
number, user name, rule name, object name or log content. The same happens with any other MCP
server the engineer adds later, without changing that server or its configuration.

**Why this priority**: this is the compliance requirement. Without it no MCP server can be
used on production data.

**Independent Test**: with `panos-mcp` in offline demo mode, and with a second, generic test
MCP server, run every tool, capture what the model receives, and confirm that none of the
servers' real values appears while the answers are still structurally correct.

**Acceptance Scenarios**:

1. **Given** a protected MCP server, **When** any of its tools returns data, **Then** every
   identifying value in the result (structured data and text) is replaced by its stand-in
   before the model reads it.
2. **Given** an MCP server added to the configuration after the guard was installed, with no
   profile, **When** its tools return data, **Then** they are protected by the default
   profile, with no action from the user.
3. **Given** the same real value appears in results from two different tools or servers, in
   the same or a later conversation, **When** both reach the model, **Then** it has the same
   stand-in in both.
4. **Given** two different real values, **When** they are pseudonymized, **Then** they get two
   different stand-ins.
5. **Given** an address object `10.1.2.0/24` and a log entry from `10.1.2.15`, **When** both are
   pseudonymized, **Then** the stand-in address still lies inside the stand-in subnet.
6. **Given** a value that carries no identifying information for that server (for
   `panos-mcp`: built-ins such as `any`, actions such as `allow`, predefined applications,
   well-known ports), **When** it appears in a result, **Then** it is passed through unchanged.
7. **Given** the guard fails while handling a result (error, timeout), **When** the tool has
   answered, **Then** the result is withheld from the model, and the model is told only that it
   was withheld.

---

### User Story 2 - Follow-up tool calls using stand-ins (Priority: P1)

The model only knows stand-ins, so its next tool calls use them ("show the rules that reference
`addr-7f3c`", "query logs for source `10.83.4.12`"). The guard translates the stand-ins in the
arguments back to real values before the MCP server receives the call.

**Why this priority**: without it multi-step investigations break.

**Independent Test**: take a stand-in from one tool result, pass it as an argument to another
tool (on the same or another server), and confirm that the server received the real value and
that the model received a pseudonymized result.

**Acceptance Scenarios**:

1. **Given** a stand-in returned earlier, **When** the model uses it as a tool argument,
   **Then** the MCP server receives the matching real value.
2. **Given** a stand-in issued for one server's result, **When** the model passes it to another
   protected server, **Then** that server also receives the real value.
3. **Given** an argument string that mixes stand-ins and literal text (a log filter, an IP
   range), **When** the call is made, **Then** each stand-in is translated and the rest is
   unchanged.
4. **Given** an argument that looks like a stand-in but matches no known real value, **When**
   the call is made, **Then** it is passed as typed. Nothing in the call or its result reveals
   other mappings.

---

### User Story 3 - Type real values in a question (Priority: P1)

The engineer asks in their own words: "why is 10.1.2.15 blocked when it goes to
fw-paris-01?". Before the question leaves the machine, the real values are replaced by the
same stand-ins the tool results use.

**Why this priority**: users naturally type hostnames, IPs and names. If those reached the
model, Story 1 would be broken by the first question.

**Independent Test**: submit questions containing known real values, capture what is sent to
the model provider, and check that it contains only stand-ins that match those in tool
results.

**Acceptance Scenarios**:

1. **Given** a question containing a real IP, network, hostname, FQDN, serial, user, e-mail or
   MAC address, **When** it is submitted, **Then** the model receives that value as its
   stand-in.
2. **Given** a question containing a name that a protected server has returned before, or that
   is known through that server's profile (for `panos-mcp`: device groups, templates,
   firewalls, rules, objects, tags, zones), **When** it is submitted, **Then** the model
   receives that name as its stand-in.
3. **Given** a real value typed in a question and the same value later returned by a tool,
   **When** both reach the model, **Then** they have the same stand-in.
4. **Given** a question that cannot be checked (for example the local secret is unreadable),
   **When** it is submitted, **Then** it is blocked with a plain-language explanation and does
   not reach the model.
5. **Given** the question has been pseudonymized, **When** it is shown back to the user in the
   conversation, **Then** the user sees it as typed, with the replaced values marked.
6. **Given** a question that carries an image, file or document attachment, **When** it is
   submitted, **Then** it is blocked and does not reach the model, and the user is asked to
   paste the text instead.

---

### User Story 4 - See the real values on screen (Priority: P2)

The assistant's answer, and the tool calls and results shown in the conversation, refer to
stand-ins. On the user's screen they are shown with the real values. Nothing about this goes
back to the model.

**Why this priority**: answers are hard to act on without it, but the compliance goal is met
without it.

**Independent Test**: in Claude Code, ask a question whose answer contains stand-ins and check
that the screen shows every stand-in as its real value, with the rest of the text unchanged.

**Acceptance Scenarios**:

1. **Given** an answer containing stand-ins, **When** it is displayed, **Then** every known
   stand-in is shown as its real value, and all other text is unchanged.
2. **Given** the user is working in Claude Code in a terminal on their own machine, **When**
   the assistant writes an answer, **Then** the user sees it with real values, without running
   any command.
3. **Given** a stand-in that the model altered or invented, **When** it is displayed, **Then**
   it is left as it is and marked as unknown, never guessed.
4. **Given** the conversation is displayed on a remote device (phone or web), **When** it is
   drawn there, **Then** it shows stand-ins only, because revealed values must not leave the
   machine.
5. **Given** revealed values on screen, **When** the user reads them, **Then** it is clear which
   values were revealed (for example by highlighting).
6. **Given** an answer has been shown with real values, **When** the conversation continues,
   **Then** the model still sees only the stand-in version.
7. **Given** the user starts Claude Code in the VS Code extension or the desktop app, **When**
   they submit a question or a protected tool returns data, **Then** the question is blocked
   and the result is withheld, with a message to use Claude Code in a terminal.

---

### User Story 5 - Add a new MCP server with precise handling (Priority: P2)

The engineer adds a new MCP server for debugging. It is protected at once by the default
profile, which hides more than necessary (some harmless values become stand-ins). The engineer,
or the server's author, adds a profile for it: which fields are names, addresses or free text,
and which values are safe vocabulary. From then on that server's results keep their harmless
values readable.

**Why this priority**: it makes the guard usable with many servers. The default profile is
already safe, so this improves quality, not compliance.

**Independent Test**: connect a test MCP server, run a tool with the default profile, add a
profile, run it again, and compare: no real identifying value in either run, and fewer
needless stand-ins in the second.

**Acceptance Scenarios**:

1. **Given** a server with no profile, **When** its results are pseudonymized, **Then** any
   value whose kind cannot be determined is treated as identifying (fail closed).
2. **Given** a profile for that server, **When** its results are pseudonymized, **Then** fields
   and values the profile marks as safe pass through unchanged, and fields it classifies use
   the matching stand-in kind.
3. **Given** a profile with an error (unreadable, invalid), **When** the server is used, **Then**
   the guard falls back to the default profile for that server and tells the user. It never
   passes data through unprotected.
4. **Given** the guard ships with a profile for `panos-mcp`, **When** `panos-mcp` is used,
   **Then** that profile applies with no setup.

---

### User Story 6 - Operator control and transparency (Priority: P3)

The person who installs the guard can see that it is active, which servers it protects, which
profile each uses, and which categories of data it covers. They can list values that are safe
to pass through (for example public DNS servers) or that must always be hidden. They can
exempt a server that handles no sensitive data. Pseudonymization itself cannot be turned off
for a protected server.

**Why this priority**: needed for adoption and audit; the defaults are already safe.

**Independent Test**: start Claude Code with the guard and several MCP servers, check the
reported status, add a keep value and an exemption, and check their effect.

**Acceptance Scenarios**:

1. **Given** any settings, **When** a session starts, **Then** the guard reports that it is
   active and lists the protected servers and their profiles.
2. **Given** an operator keep list, **When** those values appear, **Then** they pass through
   unchanged.
3. **Given** an operator exempts a server by name, **When** that server's tools are used,
   **Then** their data is not pseudonymized, and the status shows the exemption.
4. **Given** the local secret is missing on first use, **When** the guard starts, **Then** it
   creates one. **Given** it exists but cannot be read, **Then** no protected tool result and no
   question reaches the model until it is fixed.
5. **Given** the guard is not installed or not loaded, **When** the user works with MCP
   servers, **Then** nothing is protected. The documentation states this clearly; detecting it
   is out of scope.

---

### Edge Cases

- **Stand-in equal to a real value**: a stand-in IP may equal another real IP. Because the
  model only ever sees stand-ins, every value coming back from the model is read as a stand-in,
  so reveal and translation stay unambiguous. Name stand-ins use a reserved form.
- **Values inside free text**: descriptions, log fields such as URLs, file names, user agents,
  and plain-text tool output may contain identifying data inside longer text. Embedded values
  of a known shape are replaced in place. Text that cannot be checked is replaced as a whole.
- **Partial values**: IP ranges, CIDRs, FQDNs with subdomains and `DOMAIN\user` keep their
  structure (range order, subnet containment, shared parent domain).
- **Special addresses**: private, public, loopback, multicast and broadcast addresses keep their
  class.
- **Tool results that are not text**: images, files or binary content from an MCP tool cannot
  be checked and are withheld from the model, with a notice.
- **Very large results**: pseudonymizing a large result must not noticeably slow the
  conversation (see SC-006). If it cannot finish in time, the result is withheld, not passed
  through.
- **Ordinary words that match names**: a name such as `web`, `inside` or `test` must not turn
  every use of that word in a question into a stand-in. Such names are replaced only where
  they clearly refer to an item; the user sees what was replaced.
- **Typos and partial names** in a question cannot be recognised and are sent as typed; the
  user sees what was replaced and can correct it.
- **Slash commands** carrying identifying values cannot be rewritten; they are blocked with a
  request to ask as a plain question.
- **Attachments** (images, files, documents) on a question cannot be checked; the question is
  blocked with a request to paste the text instead.
- **The model trying to read the mapping**: the model's own tools (shell, file reading) must not
  be able to read the secret or the mapping, or run the reveal function. This is enforced by
  Claude Code's sandbox, which the guard requires (FR-026); without it the guard refuses to
  run.
- **Lost or rotated secret**: earlier stand-ins can no longer be revealed or translated; the
  user is told so in plain language instead of seeing wrong values.
- **Exempted server returning a stand-in**: values from an exempt server are passed through as
  is; stand-ins in arguments to an exempt server are still translated, so it receives real
  values.
- **Several users**: different local secrets give different stand-ins; stand-ins cannot be
  shared between users.

## Requirements *(mandatory)*

### Functional Requirements

**Scope and placement**

- **FR-001**: The guard MUST work inside Claude Code on the user's machine. It MUST NOT require
  any change to MCP servers or to the MCP server configuration.
- **FR-002**: Every MCP server MUST be protected by default, including servers added after the
  guard was installed. Only an explicit operator exemption by server name removes protection.

**Pseudonymization of tool results**

- **FR-003**: The guard MUST pseudonymize every identifying value in every result of a protected
  server before the model reads it: structured data, text content and error messages.
- **FR-004**: Identifying values MUST include at least: IP addresses and networks, hostnames and
  FQDNs, URLs, device names, serial numbers, user and group names, e-mail addresses, MAC
  addresses, configuration object names (for `panos-mcp`: device groups, templates, stacks,
  rules, objects, groups, tags, zones), descriptions, and free-text and identity fields of
  logs. This list is required by company policy and is not reduced by any setting.
- **FR-005**: Values that carry no identifying information MUST pass through unchanged when the
  server's profile, or the built-in vocabulary, identifies them as safe: keywords, enum values,
  predefined applications and services, well-known ports and protocols, timestamps, counters
  and severities.
- **FR-006**: When the guard cannot determine whether a value is identifying, it MUST treat it as
  identifying (fail closed).
- **FR-007**: If the guard cannot process a result (error, timeout, unsupported content), the
  result MUST be withheld from the model, never passed through.
- **FR-008**: The same real value MUST always get the same stand-in for a given user, across
  tools, servers, conversations and restarts. Different real values MUST get different
  stand-ins.
- **FR-009**: Stand-ins MUST be of the same kind as the value they replace and keep the
  relationships the model needs: IP stand-ins keep subnet containment, range order and address
  class; FQDN stand-ins keep shared parent domains; user names keep their domain part. Name
  stand-ins MUST NOT depend on the object type or on the server: one real name has exactly one
  stand-in everywhere, so the model can correlate it across configuration, logs and servers by
  plain string equality.
- **FR-010**: No one holding only stand-ins, or a list of candidate real values, MUST be able
  to recover real values without the user's local secret.

**Tool arguments**

- **FR-011**: The guard MUST translate stand-ins in the arguments of every tool call to a
  protected or exempted MCP server back to real values before the server receives the call.
- **FR-012**: Arguments MUST be read as stand-ins. A value in IP form is always translated. A
  name that is not a known stand-in is passed as typed. Translation MUST NOT reveal any mapping
  in errors or results.

**Profiles**

- **FR-013**: The guard MUST apply a default profile to any server without one. The default
  profile recognises values by shape, keeps only built-in safe vocabulary, and hides all other
  identifier-like and free-text values.
- **FR-014**: Operators MUST be able to add a profile for a server, stating which fields hold
  which kind of value and which values are safe. A profile can only make handling more
  precise. It MUST NOT be able to remove a category listed in FR-004 for fields of that kind.
- **FR-015**: An invalid or unreadable profile MUST cause a fallback to the default profile
  for that server, with a notice to the user.
- **FR-016**: The guard MUST ship with a profile for `panos-mcp`.

**User questions**

- **FR-017**: The guard MUST replace identifying values in the user's question, including text
  pasted into it, with their stand-ins before it is sent to the model provider, using the same stand-ins as tool results.
- **FR-018**: Identifying values in questions MUST be recognised by shape (IPs, networks, FQDNs,
  serials, e-mail and MAC addresses, domain user names) and by matching names known from
  earlier results and from profiles.
- **FR-019**: If a question cannot be checked, it MUST NOT be sent, and the user MUST be told
  why and how to fix it.
- **FR-020**: The user MUST be able to see which values in their question were replaced.
- **FR-032**: A question that carries an image, file or document attachment MUST NOT be sent.
  The user MUST be told to paste the text instead.

**Reveal**

- **FR-021**: In Claude Code running in a terminal, answers, the user's questions, and the tool
  calls and results shown in the conversation MUST be displayed with real values restored
  automatically. The restored text MUST NOT be sent to the model provider or stored in the
  conversation the model reads.
- **FR-022**: Reveal MUST replace only stand-ins it knows, leave all other text unchanged, and
  mark unknown stand-ins rather than guessing.
- **FR-023**: Reveal MUST happen only in the terminal. It MUST NOT happen on any other display,
  including remote or mobile views of a terminal session.
- **FR-031**: In a session that does not run in a terminal (the VS Code extension, the desktop
  app), the guard MUST block every question and withhold every protected tool result, and tell
  the user to use Claude Code in a terminal. It MUST NOT pass data through instead.

**Secret, mapping and self-protection**

- **FR-024**: The secret and the mapping MUST stay on the user's machine, be readable only by
  that user, and never appear in anything sent to the model, in errors or in logs.
- **FR-025**: If the secret is missing on first use, the guard MUST create one. If it exists but
  cannot be read, the guard MUST block questions and protected tool results until it is fixed.
- **FR-026**: The guard MUST prevent the model's own tools from reading the secret or the
  mapping, or running the reveal function. The guard MUST run only when Claude Code's sandbox
  is enabled with reads of the guard's folder denied. Otherwise it MUST block every question
  and withhold every protected tool result, and tell the user how to enable it.

**Operation and transparency**

- **FR-027**: Pseudonymization MUST always be on for protected servers and questions. There
  MUST be no setting that turns it off globally.
- **FR-028**: Operators MUST be able to list values that are always kept and values that are
  always hidden.
- **FR-029**: At the start of each session, the guard MUST show that it is active, the protected
  and exempted servers and the profile of each. It MUST tell the model that values are
  stand-ins, so the model does not present them as real or try to guess them.
- **FR-030**: Documentation MUST explain what is sent to the model provider, what is not
  covered (the model's built-in tools' output, other clients), that questions with attachments
  are blocked, how to add a
  profile, and that the guard must be installed for any protection to apply.

### Key Entities

- **Identifying value**: a real value from an MCP server's result or a user's question that
  identifies the organisation, its people, its network or its devices. Has a kind (IP,
  network, FQDN, user, name of an object type, free text…).
- **Stand-in**: the replacement the model sees; same kind and shape, consistent per user.
- **Pseudonymization secret**: per-user local secret that determines all stand-ins.
- **Mapping record**: local record of issued stand-ins and their real values, and of known
  names, used for translation, reveal and question recognition.
- **Profile**: per-server description of fields, kinds and safe vocabulary; a default profile
  applies when none exists.
- **Protected server / exemption**: which MCP servers the guard handles; all, minus explicit
  exemptions.
- **Keep list / hide list**: operator overrides of the classification.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every `panos-mcp` tool in offline demo mode, and for every tool of a generic
  test MCP server using only the default profile, zero real identifying values reach the
  model.
- **SC-002**: The answers to the `panos-mcp` acceptance questions are the same with the guard
  as without it, once revealed, for 100% of the questions that do not depend on the literal
  text of a name.
- **SC-003**: 100% of stand-ins taken from a tool result and used as arguments return the same
  records as the real values would, on the same server and across servers.
- **SC-004**: The same real value gets the same stand-in in 100% of repeated runs, including
  after restarting Claude Code.
- **SC-005**: Displayed answers show 100% of known stand-ins as their real values, with no
  visible delay.
- **SC-006**: The guard adds less than 1 second to a tool call for a result of typical size
  (up to 500 records), and less than 1 second to submitting a question.
- **SC-007**: For a test set of questions containing known real values of every category,
  zero real values reach the model provider, and 100% of the stand-ins match those in tool
  results.
- **SC-008**: A new MCP server is protected the moment it is added, and a profile for it can be
  written and applied in under 30 minutes using the documentation.
- **SC-009**: A compliance reviewer can confirm from the documentation alone, in under
  15 minutes, which data leaves the machine and in what form.

## Assumptions

- The model provider, the network path to it and anything stored remotely are outside the
  user's control; only the user's machine and the MCP servers' data sources are trusted.
- Claude Code is the only supported client. Its plugin interface allows rewriting questions
  before sending, rewriting tool-call arguments and results, and changing the display without
  changing what the model reads (confirmed against Claude Code 2.1.301; see research.md R1).
  Display changes work only in the terminal, so only Claude Code in a terminal is supported;
  the VS Code extension and the desktop app are refused (FR-031) until they allow it. Other
  clients are out of scope.
- Claude Code's sandbox is available on the supported platforms (macOS, Linux) and can deny
  reads of a folder to the model's tools. The guard requires it (FR-026).
- Covered: MCP tool calls and results, and questions, including text pasted into them.
  Questions with attachments are blocked (FR-032). Not covered: the output of Claude Code's
  built-in tools (shell commands, file reads, web fetches). The documentation states this.
  Protecting built-in tool output may be a later feature.
- The guard is a separate project. `panos-mcp` is not changed; its profile ships with the
  guard. `panos-mcp`'s offline demo mode is the reference test environment.
- A profile is precise only for servers whose results are structured. Plain-text results get
  shape detection and whole-text hiding, so they are safe but less readable.
- Pseudonymization hides values, not structure: the model still sees how many items exist and
  how they relate.
- Stand-ins are consistent per user, not across a team.
- Values in tool descriptions, schemas and built-in vocabulary are not considered sensitive.
