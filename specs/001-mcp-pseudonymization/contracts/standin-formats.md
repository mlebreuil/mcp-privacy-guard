# Contract: Stand-in Formats

What the model sees in place of each kind of value (research R7). The session system-prompt
section tells the model they are stand-ins. Every stand-in is computed from the session's
secret and is valid only in that session (research R13). Changing a format invalidates stand-ins already
issued, so it is a breaking change that needs a migration note and a MAJOR engine version.

`t(n)` = the first `n` characters of base32 (lower case, no padding) of
HMAC-SHA256(session secret, domain ‖ 0x1f ‖ value ‖ 0x1f ‖ attempt). `attempt` starts at 0.
Name and label tokens are `t(6)`, TEXT tokens `t(8)`. On a collision (checked against the
session's mapping, which holds every stand-in of the session) `attempt` goes up by 1 and the
token grows by 2 characters. MAC and DIGITS stand-ins are keyed Feistel permutations (MAC: the 46 bits other than the two
low bits of the first octet, which are fixed to `10`; DIGITS: every digit string of the same
length, so a stand-in may start with 0), so they
never collide.

| Kind | Domain | Real example | Stand-in example | Preserved |
|---|---|---|---|---|
| IP (private v4) | Crypto-PAn | `10.1.2.15` | `10.83.4.12` | special block, every shared prefix length |
| IP (prefix) | Crypto-PAn | `10.1.2.0/24` | `10.83.4.0/24` | contains the stand-in of `10.1.2.15` |
| IP (range) | Crypto-PAn | `10.1.2.1-10.1.2.50` | `10.83.4.9-10.83.4.60` | order, shared prefix |
| IP (public v4) | Crypto-PAn | `52.10.3.7` | `52.201.77.140` | first octet, publicness |
| IP (v6 global) | Crypto-PAn | `2a01:e0a::5` | `2a01:9c3f:…` | first 16 bits, prefixes |
| IP (unchanged) | — | `0.0.0.0/0`, `255.255.255.0`, `any`, documentation ranges | same | — |
| FQDN | `label` + parent chain | `app.corp.example.com` | `h-wx2qr4.d-k7qaw2.d-p4mzc6.com` | public suffix, shared parents |
| URL | as parts | `https://intranet.corp.example.com:8443/hr?id=3` | `https://h-….d-….d-….com:8443/p-r4t6vq` | scheme, port, host form |
| EMAIL | `user` + FQDN | `jdoe@corp.example.com` | `u-3hd7qa@d-k7qaw2.d-p4mzc6.com` | domain consistency |
| USER | `dom`, `user` | `CORP\jdoe` | `dom-x2a7yq\u-3hd7qa` | domain part |
| GROUP | `dom`, `group` | `CORP\net-admins` | `dom-x2a7yq\g-…` | domain part |
| MAC | `mac` | `00:1b:17:aa:bb:cc` | `02:5e:91:0c:7d:e3` | form; locally administered unicast; vendor OUI hidden |
| DIGITS | `digits` | `007951000123456` | `493810774026518` | length, digits only (a leading zero may appear) |
| NAME and every profile name kind | `name` | `fw-paris-01` (device, rule, object…) | `n-k3f7qa` | one stand-in per real name, whatever its kind |
| TEXT | `text` | any description | `text-q6w2m4p3` | equality only |
| MIXED | as parts | `Object web-srv-01 not found` | `Object n-a7zekm not found` | known words |

## Guarantees

1. **Consistent within the session**: the same value gives the same stand-in across tools,
   servers, turns and engine processes of one session (FR-008).
2. **Distinct**: no two real values share a stand-in or a token within a session.
3. **One name, one stand-in**: a real name has the same stand-in in every field, tool and
   server, whatever kind a profile gives it, so the model correlates by string equality
   (FR-009).
4. **Opaque**: no stand-in can be computed or inverted without the secret (FR-010).
5. **Recognisable**: name, TEXT and FQDN-label stand-ins match
   `\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b`. `status.recognise` gives the exact regex. IP
   stand-ins cannot be told apart from IPs by shape.
6. **Session-only**: a new session has a new secret, so the same value gets an unrelated
   stand-in. When the session ends its secret and mapping are deleted, and none of its
   stand-ins, IPs included, can be revealed or translated again (FR-008, FR-025).
