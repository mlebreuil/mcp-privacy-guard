# Contract: Stand-in Formats

What the model sees in place of each kind of value (research R7). The session system-prompt
section tells the model they are stand-ins. Changing a format invalidates stand-ins already
issued, so it is a breaking change that needs a migration note and a MAJOR engine version.

`t(n)` = the first `n` characters of base32 (lower case, no padding) of
HMAC-SHA256(secret, domain ‖ 0x1f ‖ value ‖ 0x1f ‖ attempt). `attempt` starts at 0. On a
collision the suffix grows by 2 characters.

| Kind | Domain | Real example | Stand-in example | Preserved |
|---|---|---|---|---|
| IP (private v4) | Crypto-PAn | `10.1.2.15` | `10.83.4.12` | special block, every shared prefix length |
| IP (prefix) | Crypto-PAn | `10.1.2.0/24` | `10.83.4.0/24` | contains the stand-in of `10.1.2.15` |
| IP (range) | Crypto-PAn | `10.1.2.1-10.1.2.50` | `10.83.4.9-10.83.4.60` | order, shared prefix |
| IP (public v4) | Crypto-PAn | `52.10.3.7` | `52.201.77.140` | first octet, publicness |
| IP (v6 global) | Crypto-PAn | `2a01:e0a::5` | `2a01:9c3f:…` | first 16 bits, prefixes |
| IP (unchanged) | — | `0.0.0.0/0`, `255.255.255.0`, `any`, documentation ranges | same | — |
| FQDN | `label` + parent chain | `app.corp.example.com` | `h-9x2q.d-k7qa.d-p1mz.com` | public suffix, shared parents |
| URL | as parts | `https://intranet.corp.example.com:8443/hr?id=3` | `https://h-….d-….d-….com:8443/p-r4t8vq` | scheme, port, host form |
| EMAIL | `user` + FQDN | `jdoe@corp.example.com` | `u-3hd8qa@d-k7qa.d-p1mz.com` | domain consistency |
| USER | `dom`, `user` | `CORP\jdoe` | `dom-x2a9\u-3hd8qa` | domain part |
| GROUP | `dom`, `group` | `CORP\net-admins` | `dom-x2a9\g-…` | domain part |
| MAC | `mac` | `00:1b:17:aa:bb:cc` | `02:5e:91:0c:7d:e3` | form; vendor OUI hidden |
| DIGITS | `digits` | `007951000123456` | `493810774026518` | length, digits only |
| NAME and every profile name kind | `name` | `fw-paris-01` (device, rule, object…) | `n-k3f9qa` | one stand-in per real name, whatever its kind |
| TEXT | `text` | any description | `text-q8w2m4p1` | equality only |
| MIXED | as parts | `Object web-srv-01 not found` | `Object n-a91ezk not found` | known words |

## Guarantees

1. **Deterministic**: the same secret and value give the same stand-in, across processes and
   restarts (FR-008).
2. **Distinct**: no two real values share a stand-in or a name token.
3. **One name, one stand-in**: a real name has the same stand-in in every field, tool and
   server, whatever kind a profile gives it, so the model correlates by string equality
   (FR-009).
4. **Opaque**: no stand-in can be computed or inverted without the secret (FR-010).
5. **Recognisable**: name, TEXT and FQDN-label stand-ins match
   `\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b`. `status.recognise` gives the exact regex. IP
   stand-ins cannot be told apart from IPs by shape.
