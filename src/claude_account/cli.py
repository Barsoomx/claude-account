"""Switch between multiple Claude Code accounts by swapping local credentials.

Only the subscription token (``claudeAiOauth``) and the account identity
(``oauthAccount``) are swapped. MCP auth (``mcpOAuth``) and all project state
in ``~/.claude.json`` are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from claude_account import __version__

_SLOT_RE = re.compile(r'[a-z0-9_-]+')


class AccountError(Exception):
    pass


def _home() -> Path:
    return Path.home()


def cred_file() -> Path:
    return Path(os.environ.get('CLAUDE_CRED_FILE', _home() / '.claude' / '.credentials.json'))


def config_file() -> Path:
    return Path(os.environ.get('CLAUDE_CONFIG_FILE', _home() / '.claude.json'))


def accounts_dir() -> Path:
    return Path(os.environ.get('CLAUDE_ACCOUNTS_DIR', _home() / '.claude-accounts'))


def backups_dir() -> Path:
    return accounts_dir() / 'backups'


def _ts() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def _valid_slot(name: str) -> bool:
    return bool(name) and _SLOT_RE.fullmatch(name) is not None


def _load_json(path: Path):
    try:
        with path.open() as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def _atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.tmp.')
    try:
        with os.fdopen(fd, 'w') as fh:
            json.dump(obj, fh, indent=2)
            fh.write('\n')
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass

        raise


def _dig(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None

        obj = obj.get(key)

    return obj


def _ensure_accounts_dir() -> None:
    accounts_dir().mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(accounts_dir(), 0o700)
    except OSError:
        pass


def _slot_path(name: str) -> Path:
    return accounts_dir() / f'{name}.json'


def _iter_slots() -> list[Path]:
    directory = accounts_dir()
    if not directory.is_dir():
        return []

    return sorted(p for p in directory.glob('*.json') if not p.name.startswith('.'))


def _slot_for_uuid(uuid: str):
    if not uuid:
        return None

    for path in _iter_slots():
        data = _load_json(path) or {}
        if data.get('accountUuid') == uuid:
            return path.stem

    return None


def _build_slot(cred, cfg, slot: str) -> dict:
    return {
        'slot': slot,
        'label': _dig(cfg, 'oauthAccount', 'emailAddress') or 'unknown',
        'accountUuid': _dig(cfg, 'oauthAccount', 'accountUuid') or '',
        'subscriptionType': _dig(cred, 'claudeAiOauth', 'subscriptionType') or 'unknown',
        'capturedAt': _ts(),
        'claudeAiOauth': _dig(cred, 'claudeAiOauth'),
        'oauthAccount': _dig(cfg, 'oauthAccount'),
    }


def _prune_backups(keep: int = 10) -> None:
    directory = backups_dir()
    if not directory.is_dir():
        return

    dirs = sorted(
        (p for p in directory.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in dirs[keep:]:
        shutil.rmtree(path, ignore_errors=True)


def cmd_capture(slot: str) -> None:
    if not _valid_slot(slot):
        raise AccountError('usage: claude-account capture <slot>  (slot = lowercase letters/digits/-/_)')

    if not shutil.which('claude'):
        raise AccountError("'claude' CLI not found in PATH")

    _ensure_accounts_dir()
    booth = Path(tempfile.mkdtemp(prefix='claude-booth.'))
    try:
        print(f"== Login booth for slot '{slot}' ==", file=sys.stderr)
        print('A fresh, isolated Claude Code will open — your host login is NOT touched.', file=sys.stderr)
        print(f"  1) Log in with the account you want to store in '{slot}'.", file=sys.stderr)
        print('  2) At the prompt, type /exit (or Ctrl+C) to come back here.', file=sys.stderr)
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(booth))
        subprocess.run(['claude'], env=env)
        cred = _load_json(booth / '.credentials.json')
        if not _dig(cred, 'claudeAiOauth', 'accessToken'):
            raise AccountError('login not completed (no OAuth token captured)')

        cfg = _load_json(booth / '.claude.json')
        slot_obj = _build_slot(cred, cfg, slot)
        _atomic_write_json(_slot_path(slot), slot_obj)
        print(f"captured slot '{slot}': {slot_obj['label']}  [{slot_obj['subscriptionType']}]")
    finally:
        shutil.rmtree(booth, ignore_errors=True)


def cmd_snapshot(slot: str) -> None:
    if not _valid_slot(slot):
        raise AccountError('usage: claude-account snapshot <slot>')

    cred = _load_json(cred_file())
    if not _dig(cred, 'claudeAiOauth', 'accessToken'):
        raise AccountError(f"no active credentials at {cred_file()} — log in with 'claude' first")

    cfg = _load_json(config_file())
    _ensure_accounts_dir()
    slot_obj = _build_slot(cred, cfg, slot)
    _atomic_write_json(_slot_path(slot), slot_obj)
    print(f"snapshotted current host account into slot '{slot}': {slot_obj['label']}")


def cmd_status() -> None:
    _ensure_accounts_dir()
    cfg = _load_json(config_file())
    huuid = _dig(cfg, 'oauthAccount', 'accountUuid') or ''
    hemail = _dig(cfg, 'oauthAccount', 'emailAddress') or ''
    active = _slot_for_uuid(huuid)
    print(f"host active account: {hemail or '<none>'}")
    if huuid and not active:
        print('  (not captured in any slot — run: claude-account capture <slot>)')

    print()
    print(f'slots in {accounts_dir()}:')
    slots = _iter_slots()
    if not slots:
        print('  (none yet)')

        return

    for path in slots:
        data = _load_json(path) or {}
        mark = '*' if path.stem == active else ' '
        label = data.get('label', '?')
        sub = data.get('subscriptionType', '?')
        at = data.get('capturedAt', '?')
        print(f'  {mark} {path.stem:<10} {label:<30} [{sub}]  captured {at}')


def cmd_apply(target: str) -> None:
    if not _valid_slot(target):
        raise AccountError(f"invalid slot name '{target}'")

    tobj = _load_json(_slot_path(target))
    if tobj is None:
        raise AccountError(f"slot '{target}' not found (capture it first: claude-account capture {target})")

    cfg = _load_json(config_file())
    if cfg is None:
        raise AccountError(f'host config {config_file()} not found')

    tuuid = tobj.get('accountUuid') or ''
    tlabel = tobj.get('label') or 'unknown'
    huuid = _dig(cfg, 'oauthAccount', 'accountUuid') or ''
    if huuid and huuid == tuuid:
        print(f"already on '{target}' ({tlabel}) — nothing to do")

        return

    _ensure_accounts_dir()
    cred = _load_json(cred_file())

    if cred is not None:
        _atomic_write_json(accounts_dir() / '.last-active.json', _build_slot(cred, cfg, '_last-active'))

    cur = _slot_for_uuid(huuid)
    if cur and cred is not None:
        _atomic_write_json(_slot_path(cur), _build_slot(cred, cfg, cur))
        print(f"saved current live tokens back into slot '{cur}'", file=sys.stderr)
    elif huuid:
        print(
            "warning: current host account isn't in any slot; "
            'its live tokens are only in .last-active.json',
            file=sys.stderr,
        )

    bdir = backups_dir() / _ts()
    bdir.mkdir(parents=True, exist_ok=True)
    if cred_file().exists():
        shutil.copy2(cred_file(), bdir / 'credentials.json')

    shutil.copy2(config_file(), bdir / 'claude.json')
    _prune_backups(keep=10)

    new_cred = cred if isinstance(cred, dict) else {}
    new_cred['claudeAiOauth'] = tobj.get('claudeAiOauth')
    _atomic_write_json(cred_file(), new_cred)

    cfg['oauthAccount'] = tobj.get('oauthAccount')
    _atomic_write_json(config_file(), cfg)

    print(f"switched to '{target}' ({tlabel})")
    print("restart any running 'claude' session for the change to take effect", file=sys.stderr)


def cmd_swap() -> None:
    slots = _iter_slots()
    if len(slots) < 2:
        raise AccountError(
            f'swap needs 2 captured slots (have {len(slots)}). Run: claude-account capture <slot>'
        )

    if len(slots) > 2:
        raise AccountError('more than 2 slots present — pick one: claude-account use <slot>')

    cfg = _load_json(config_file())
    huuid = _dig(cfg, 'oauthAccount', 'accountUuid') or ''
    cur = _slot_for_uuid(huuid)
    if not cur:
        raise AccountError('current host account matches no slot — pick explicitly: claude-account use <slot>')

    target = next(p.stem for p in slots if p.stem != cur)
    cmd_apply(target)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='claude-account',
        description='Manually switch between multiple Claude Code accounts (subscriptions).',
    )
    parser.add_argument('-V', '--version', action='version', version=f'claude-account {__version__}')
    sub = parser.add_subparsers(dest='cmd')

    p_capture = sub.add_parser('capture', help='log in (isolated) and store ANOTHER account into <slot>')
    p_capture.add_argument('slot')

    p_snapshot = sub.add_parser('snapshot', aliases=['save'], help='store the account you are ALREADY logged into')
    p_snapshot.add_argument('slot')

    sub.add_parser('status', aliases=['st'], help='show the active account and stored slots')
    sub.add_parser('swap', aliases=['toggle'], help='toggle between the two stored slots')

    p_use = sub.add_parser('use', aliases=['switch'], help='activate a specific slot')
    p_use.add_argument('slot')

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'capture':
            cmd_capture(args.slot)
        elif args.cmd in ('snapshot', 'save'):
            cmd_snapshot(args.slot)
        elif args.cmd in ('status', 'st'):
            cmd_status()
        elif args.cmd in ('swap', 'toggle'):
            cmd_swap()
        elif args.cmd in ('use', 'switch'):
            cmd_apply(args.slot)
        else:
            parser.print_help(sys.stderr)

            return 1
    except AccountError as exc:
        print(f'error: {exc}', file=sys.stderr)

        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
