# claude-account

[![PyPI](https://img.shields.io/pypi/v/claude-account.svg)](https://pypi.org/project/claude-account/)
[![Python versions](https://img.shields.io/pypi/pyversions/claude-account.svg)](https://pypi.org/project/claude-account/)
[![CI](https://github.com/Barsoomx/claude-account/actions/workflows/ci.yml/badge.svg)](https://github.com/Barsoomx/claude-account/actions/workflows/ci.yml)
[![CodeQL](https://github.com/Barsoomx/claude-account/actions/workflows/codeql.yml/badge.svg)](https://github.com/Barsoomx/claude-account/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/Barsoomx/claude-account/graph/badge.svg)](https://codecov.io/gh/Barsoomx/claude-account)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Manually switch between multiple **Claude Code** accounts (e.g. a personal and a
work subscription) from the terminal — without signing out and back in.

It swaps **only** the subscription token and account identity, leaving your MCP
server auth and all project state untouched:

- `claudeAiOauth` in `~/.claude/.credentials.json` — the subscription token
- `oauthAccount` in `~/.claude.json` — the account identity

Everything else — `mcpOAuth`, project history, settings — is preserved. Each
switch backs up your host files first.

> **Disclaimer.** This is an unofficial, community tool. It is **not affiliated
> with, endorsed by, or sponsored by Anthropic**. "Claude" and "Anthropic" are
> trademarks of Anthropic, PBC. It only shuffles credential files that already
> live on your own machine; it talks to no Anthropic service itself. Use it to
> switch between accounts **you personally own**, manually. Don't use it to
> automate around usage limits.

## Install

```bash
# run without installing
uvx claude-account status

# or install as a persistent tool
uv tool install claude-account
# or
pipx install claude-account
```

Requires the [`claude`](https://claude.com/claude-code) CLI on your `PATH`
(only for `capture`) and Python 3.9+.

## Quick start

Two accounts, called `primary` and `backup`:

```bash
claude-account snapshot primary   # store the account you're already on
claude-account capture  backup    # opens an isolated login for the 2nd account
claude-account swap               # flip between them
```

Handy shell aliases:

```bash
alias cas='claude-account swap'
alias cass='claude-account status'
```

## Commands

| Command | What it does |
| --- | --- |
| `snapshot <slot>` | Store the account you are **already** logged into (no re-login). |
| `capture <slot>` | Open an isolated login booth and store **another** account. |
| `status` | Show the active account and stored slots. |
| `swap` | Toggle between the two stored slots. |
| `use <slot>` | Activate a specific slot. |

Slots live in `~/.claude-accounts/`; host backups in
`~/.claude-accounts/backups/`. Paths can be overridden with
`CLAUDE_CRED_FILE`, `CLAUDE_CONFIG_FILE`, and `CLAUDE_ACCOUNTS_DIR`.

## How it works

`capture` logs in inside a throwaway `CLAUDE_CONFIG_DIR`, so your host login is
never touched, then copies out just that account's `claudeAiOauth` +
`oauthAccount`. `swap`/`use` do the reverse surgically: they write the target
slot's `claudeAiOauth` into `.credentials.json` and its `oauthAccount` into
`.claude.json`, preserving every other key. Before switching away, the current
account's live tokens are saved back into its slot (Claude Code rotates refresh
tokens, so stale copies would eventually stop working).

Do a switch **between** `claude` sessions — a running session holds its token in
memory. Slot files contain refresh tokens; treat them as secrets (they are
written `0600` and `~/.claude-accounts/` is `0700`).

## Development

```bash
uv run --group dev pytest -q --cov=claude_account
uv build
```

[![coverage sunburst](https://codecov.io/gh/Barsoomx/claude-account/graphs/tree.svg?token=0E9LK67P0B)](https://codecov.io/gh/Barsoomx/claude-account)

## Releasing

Tag a version and push; CI builds and publishes to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no
tokens):

```bash
git tag v0.1.0
git push origin v0.1.0
```

## License

MIT — see [LICENSE](LICENSE).
