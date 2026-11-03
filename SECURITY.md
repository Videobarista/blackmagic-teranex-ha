# Security Policy

## Supported versions

Only the most recent release receives security fixes.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| Older releases | No |

## Reporting a vulnerability

Please report security issues privately through GitHub's
[security advisory form](https://github.com/Videobarista/blackmagic-teranex-ha/security/advisories/new)
rather than in a public issue.

Expect an initial response within 14 days. This is a hobby project maintained
in spare time, so please allow reasonable time for a fix before any public
disclosure.

## Scope

This integration talks to a Teranex over the Blackmagic Teranex Ethernet
Protocol on TCP port 9800.

### What the protocol cannot do

**The protocol has no authentication and no encryption.** Anyone who can reach
port 9800 can read and change every setting, including overwriting presets.
The unit's *Remote lock* blocks Teranex Setup but still allows this
connection. No integration can add a password or TLS to the device, so the
network has to provide that protection.

### What the integration does

- Every value sent to the unit is checked first. Line breaks, colons in names
  and over-long values are refused, so no input can smuggle extra commands
  into the line-based protocol.
- Everything the unit sends is treated as untrusted: line length, block and
  field counts, and name and value lengths are capped, non-numeric and
  non-finite numbers are ignored, and a malformed reply leads to a clean
  reconnect rather than a crash or growing memory use.
- The host, port and output format names are validated in the config and
  options flows.
- One persistent connection, commands one at a time with a wait for each
  reply, reconnects backing off from 5 seconds to once a minute, and a
  keepalive every 30 seconds. The unit is never flooded.
- Only the host, port, friendly name, model and firmware version are stored.
  No credentials exist to store.
- Connections are outbound only. The integration opens no listening ports.
- No runtime dependencies beyond Home Assistant itself.

### Recommended network setup

- Put the Teranex on an AV or production VLAN.
- Allow TCP 9800 to the Teranex only from the Home Assistant host and from
  any other control software you use.
- Allow Teranex Setup only from the machine you configure the unit with.
- Block all other inbound traffic to the Teranex, including from guest and
  IoT networks, and do not forward any port to it from the internet.
- The Teranex needs no internet access; block its outbound traffic.
- Give it a DHCP reservation or a static address.

Vulnerabilities in the Teranex firmware itself belong to Blackmagic Design,
not to this repository.
