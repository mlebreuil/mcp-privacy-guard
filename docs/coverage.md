# What the guard covers, and what it does not

For compliance reviewers. It takes about 15 minutes to read. The guard is a local
pseudonymization layer between your MCP servers and the model provider. Everything it does
happens on your machine; the engine opens no network listener and contacts no data source.

## What leaves the machine, and in what form

The model provider receives your conversation. With the guard, the identifying values in it are
stand-ins, not real values:

| Real value | What the provider sees | What is preserved |
|---|---|---|
| IP address, network, range | another address of the same kind, e.g. `10.1.2.15` → `10.83.4.12` | special block, shared prefixes (a network still contains its hosts), first octet of a public address |
| Host name / FQDN | `h-wx2qr4.d-k7qaw2.d-p4mzc6.com` | public suffix, shared parent domains |
| URL | same scheme and port, stand-in host and path | scheme, port |
| E-mail, user, group | `u-3hd7qa@d-k7qaw2.d-p4mzc6.com`, `dom-x2a7yq\u-3hd7qa` | domain consistency |
| MAC address | a locally administered address | form only |
| Long digit strings (serials) | digits of the same length | length |
| Names (devices, rules, objects, …) | `n-k3f7qa` | equality: the same name is the same string everywhere |
| Free-text descriptions | `text-q6w2m4p3` | equality only |
| Text with identifying parts | the parts replaced in place (`Object n-a7zekm not found`) | the plain words around them |

The full list is in `specs/001-mcp-pseudonymization/contracts/standin-formats.md`.

Not replaced, so the provider does see them: numbers, booleans, timestamps and durations, words
from the built-in and profile vocabulary, enum values a profile lists, object keys that are plain
words (`state`, `summary`), tool names and MCP server aliases, and the structure of every result.
Values on the operator keep list and everything an exempt server returns reach the provider
unchanged, by decision of the operator.

## What is covered

- **MCP tool results**, from every connected server, with no change to the server or to the MCP
  configuration. A result that cannot be processed is withheld, never passed on.
- **Tool arguments**: when the model uses a stand-in in a call, the guard translates it back to
  the real value before the tool runs, so answers are correct for the real data. A stand-in it
  does not know is left as typed.
- **Your questions**, including pasted text, and slash-command arguments and skill text:
  identifying shapes and names the guard has seen are replaced before the question is sent.
- **Reveal**: in the terminal only, the real values are drawn on your screen in place of the
  stand-ins. The transcript and the model keep the stand-ins.

## What is blocked

The guard fails closed. In each case below, nothing reaches the model and the user is told why
(`/privacy-guard` shows the current reason):

- a question with an attachment (image, file or document): paste the text instead;
- a session that is not drawn in a terminal (VS Code extension, desktop app, headless);
- missing sandbox settings (sandbox on, the guard folder denied to reads, no unsandboxed
  commands, no silent fallback);
- a resumed conversation: its stand-ins belong to a session that ended;
- an expired or unreadable session store;
- a Claude Code older than 2.1.303 or an engine that cannot be started;
- questions until every server warm-up has finished (names are learned first), and for good
  if a warm-up fails, until it is fixed or the server is exempted.

## Session-only stand-ins

Every Claude Code session has its own secret and its own mapping, created when the session
starts. Stand-ins of one session mean nothing in another, and the same value gets a different
stand-in each time.

- The secret and mapping are deleted when the session ends (`/exit`, `/clear`). After that no
  stand-in of the session can be revealed or translated again, IP addresses included.
- If a session crashes, its folder is swept by the next session start once it has been
  untouched for 24 hours.
- Deletion is a plain unlink, not a secure wipe. Use full-disk encryption on machines where this
  matters.
- Nothing that links stand-ins to real values is kept anywhere else. The secret, the mappings
  and revealed text never appear in logs, error messages or status output, and are never kept in
  host-synced storage.

## The guard is the only pseudonymization layer

MCP servers send raw data. In particular `panos-mcp` pseudonymizes nothing at runtime (it keeps
pseudonymization only for creating sample data). If the guard is not installed, the provider
receives real values.

## What is not covered

- **Output of Claude Code's built-in tools** (reading files, running commands, searching). The
  guard works on MCP data and on your questions.
- **Other clients**: any session that does not use this plugin in a terminal.
- **An uninstalled or disabled guard.** The plugin refuses to run without the sandbox settings
  and denies the model's attempts to edit Claude Code's settings or the guard's folder, but that
  protection is best effort. Pin the plugin and the sandbox in managed settings where your
  organisation can (see `install.md`).
- **Content outside text**: images and other non-text items in a tool result are replaced by a
  notice.

## Residual risks

These are known limits of the approach. They do not make the guard fail open, but a reviewer
should weigh them:

1. **Public IP addresses keep their first octet** (the /8; the first 16 bits for IPv6). The
   provider can see which block a public address belongs to.
2. **Names that are plain English words** (for example a rule called `backup`) are recognised in
   results when a profile marks the field, but in free text and in unquoted questions they can be
   missed, because they look like ordinary words.
3. **Names with spaces in questions** are only recognised when they were seen in a result first.
4. **Object keys that are common words** are kept as they are (`summary`, `state`). A key that
   itself identifies something but looks like a plain word is not hidden unless the operator
   hides it or the profile says `keys = "hide"`.
5. **Names of servers without a warm-up**, typed before a result returned them, reach the model
   as typed. A warm-up (a profile's list of read-only tools) removes this for the names it
   returns.
6. **A server that connects after the question** (or never connects) cannot be warmed up in
   time: the plugin re-lists the connected servers at every hook, so names are learned from the
   next result on, not before.
7. **A partial application list** in a profile (for example for PAN-OS): applications not in the
   list are treated as names, which is safe but less readable.
8. **Keep-list and exempt values** reach the model unchanged by design. A model can reuse a kept
   IP address; the guard recognises it and does not translate it, and refuses a call where an
   address could be either a kept value or a stand-in (it asks you to state the address).
9. **Equality is visible.** The provider can tell that two stand-ins are the same value, which
   is what lets the model reason, and can count distinct values.
