# Contract: Stand-in Formats

What the model sees in place of each kind of value (research R4). These formats are part of
the user-visible behaviour: the tool descriptions and server instructions tell the model they
are stand-ins. Changing a format invalidates stand-ins already issued, so it is a MAJOR
change.

`t(n)` = the first `n` characters of base32 (lower case, no padding) of
HMAC-SHA256(secret, kind ‖ 0x1f ‖ real ‖ 0x1f ‖ attempt). `attempt` starts at 0 and increases
on collision; on collision the suffix grows by 2 characters.

| Kind | Real example | Stand-in example | Preserved |
|---|---|---|---|
| IP (private v4) | `10.1.2.15` | `10.83.4.12` | special block (`10/8`), every shared prefix length |
| IP (prefix) | `10.1.2.0/24` | `10.83.4.0/24` | containment of `10.1.2.15` |
| IP (range) | `10.1.2.1-10.1.2.50` | `10.83.4.9-10.83.4.60` | order, shared prefix |
| IP (public v4) | `52.10.3.7` | `52.201.77.140` | first octet, publicness |
| IP (v6 global) | `2a01:e0a::5` | `2a01:9c3f:…` | first 16 bits, prefixes |
| IP (unchanged) | `0.0.0.0/0`, `255.255.255.0`, `any`, documentation ranges | same | — |
| FQDN | `app.corp.example.com` | `h-9x2q.d-k7qa.d-p1mz.com` | TLD, shared parent labels |
| URL | `https://intranet.corp.example.com/hr/pay?id=3` | `https://h-….d-….d-….com/p-r4t8vq` | scheme, host form |
| EMAIL | `jdoe@corp.example.com` | `u-3hd8@d-k7qa.d-p1mz.com` | domain consistency |
| USER | `CORP\jdoe` | `dom-x2a9\u-3hd8` | domain part, shared user token with e-mail local part only if equal |
| MAC | `00:1b:17:aa:bb:cc` | `02:5e:91:0c:7d:e3` | form; vendor OUI hidden |
| SERIAL | `007951000123456` | `990381774026` | digits only |
| DEVICE_NAME | `fw-paris-01` | `fw-k3f9qa` | |
| DEVICE_GROUP | `EMEA-Branches` | `dg-7mq2ld` | |
| TEMPLATE / TEMPLATE_STACK | `Branch-Net` | `tpl-…` / `stk-…` | |
| RULE_NAME | `allow-web-dmz` | `rule-a91ezk` | |
| ADDRESS / ADDRESS_GROUP | `web-srv-01` / `web-servers` | `addr-…` / `grp-…` | |
| SERVICE / SERVICE_GROUP | `tcp-8443` | `svc-…` / `svcg-…` | |
| APP_GROUP / PROFILE_GROUP | | `appg-…` / `prof-…` | |
| TAG / ZONE | `PCI` / `dmz-paris` | `tag-…` / `zone-…` | |
| INTERFACE (description) | | `text-…` | interface *names* such as `ethernet1/1` are `Keep` |
| VSYS (display name) | | `vsys-…` | `vsys1` IDs are `Keep` |
| GROUP | `CORP\net-admins` | `dom-x2a9\g-…` | |
| TEXT | any description, file name, user agent | `text-q8w2m4p1` | equality only |
| MIXED | `Object web-srv-01 not found in dg EMEA-Branches` | `Object addr-… not found in dg dg-7mq2ld` | built-in vocabulary |

## Guarantees

1. **Deterministic**: the same secret, kind and real value give the same stand-in, across
   processes and restarts.
2. **Distinct**: no two reals of one kind share a stand-in; name prefixes keep kinds apart.
3. **Opaque**: no stand-in can be computed or inverted without the secret.
4. **Recognisable**: name, TEXT and FQDN-label stand-ins match
   `\b(rule|addr|grp|svc|svcg|appg|prof|tag|zone|dg|tpl|stk|fw|vsys|text|dom|u|g|h|d|p)-[a-z2-7]{4,}\b`.
   Reveal uses this to mark unknown stand-ins (FR-016). IP stand-ins cannot be told apart
   from IPs by shape, so an IP that is not in the reveal table is left as is and not marked.
