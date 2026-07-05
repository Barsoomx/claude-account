# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |

Only the latest released version receives security fixes.

## Reporting a vulnerability

Please report security issues **privately** via GitHub's
[Report a vulnerability](https://github.com/Barsoomx/claude-account/security/advisories/new)
form (repository **Security → Advisories**). Do not open a public issue for
security reports.

Please include the affected version(s), reproduction steps or a proof of
concept, and an impact assessment. You can expect an initial response within a
few days.

## Scope and handling of secrets

`claude-account` only shuffles credential files that already exist on your own
machine (`~/.claude/.credentials.json`, `~/.claude.json`). It talks to no
Anthropic or third-party service itself.

Stored account slots in `~/.claude-accounts/` contain OAuth **refresh tokens** —
treat them as secrets. The tool writes slot files `0600` and keeps the directory
`0700`, and never transmits them anywhere.
