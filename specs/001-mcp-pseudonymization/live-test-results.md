# Live check results

Run 2026-10-28 18:22, Claude Code 2.1.312 (Claude Code).

| # | Check | Result | Note |
|---|---|---|---|
| 1 | start and early question | pass |  |
| 2 | /privacy-guard | pass |  |
| 3 | reveal on screen, stand-ins in the transcript | pass |  |
| 4 | follow-up with a second tool call | pass | Re-run 2026-10-28 after the fixes. |
| 5 | question with real values | pass | Re-run 2026-10-28 after the fixes. |
| 6 | manual reveal | pass |  |
| 7 | self-protection | pass |  |
| 8 | generic server: nothing leaks | pass | Re-run 2026-10-28: 0 real values. |
| 9 | profile example, then a broken profile | pass | Re-run 2026-10-28: example profile valid; broken file gives `invalid: invalid-toml`, server still protected. |
| 10 | session ends | pass |  |
| 11 | new session, new stand-ins | pass | Re-run 2026-10-28. |
| 12 | /clear | pass | Re-run 2026-10-28 after the /clear fix (turns() is not 0 after /clear). |
| 13 | --resume | pass | 2026-10-28: the resumed conversation was blocked with the ended-session message; after /clear a question went through (new session id 35486f57-…). |
| 14 | stale folder swept | pass | 2026-10-28 |
| 15 | failure paths | pass | 2026-10-28: 15a (after the fix: `the session store is unusable`), 15b (engine off PATH), 15c (denyRead removed) and 15e (attachment) pass. 15d (VS Code extension) not run live; covered by the unit test for the terminal surface. |
| 16 | failed warm-up | pass | 2026-10-28: with a self-contained profile whose warm-up tool does not exist, questions were dropped with `loading names for panorama-demo failed (tool-missing)`; after removing it and `/clear`, `panorama-demo` was `panos-mcp (valid)`, `warm-up complete`. An earlier run with a broken copy of `panos-mcp.toml` fell back to the default profile (no warm-up) and let a question through, by design. |
| 17 | exempt server | pass | 2026-10-28: with `generic` exempt, the model passed a real IP from `list_devices` to the new `echo` tool and the server answered with the same IP. |
| 18 | keep list | pass | 2026-10-28: the model sent 9.9.9.9 to `echo`; the server answered `received: 9.9.9.9`. |

## T011 facts

- Does --resume keep the original session id? **not observed**: the id before the resume was not looked up (`/status` at the start of the resumed conversation would show it).
- After /clear does the session id change, and does session.start fire again? **The id changes (a new transcript file starts with the /clear command). Whether session.start fires is not shown; the plugin follows the id at the next hook either way.**
- Does session.turns() report above 0 for a resumed session? **Yes, or it fails: the resumed conversation was blocked.** Which of the two is not known. After /clear it was not 0 (or failed): the guard blocked the new session until the fix.
- Does a forking slash command raise command.run to the plugin (IP in its arguments replaced)? **not run yet**
