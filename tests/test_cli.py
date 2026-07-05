import json
import subprocess
from pathlib import Path

import pytest

from claude_account import cli


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _load(path: Path):
    return json.loads(Path(path).read_text())


@pytest.fixture
def f_env(tmp_path, monkeypatch):
    cred = tmp_path / 'host' / '.claude' / '.credentials.json'
    cfg = tmp_path / 'host' / '.claude.json'
    acc = tmp_path / 'accounts'
    monkeypatch.setenv('CLAUDE_CRED_FILE', str(cred))
    monkeypatch.setenv('CLAUDE_CONFIG_FILE', str(cfg))
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(acc))

    _write(cred, {
        'claudeAiOauth': {
            'accessToken': 'ACCESS-A', 'refreshToken': 'REFRESH-A', 'subscriptionType': 'max',
        },
        'mcpOAuth': {'gitlab': {'access_token': 'MCP-SECRET'}},
    })
    _write(cfg, {
        'oauthAccount': {'accountUuid': 'UUID-A', 'emailAddress': 'a@example.com'},
        'projects': {'/x': {'history': [1, 2, 3]}},
        'numStartups': 42,
    })
    _write(acc / 'primary.json', {
        'slot': 'primary', 'label': 'a@example.com', 'accountUuid': 'UUID-A',
        'subscriptionType': 'max', 'capturedAt': 't0',
        'claudeAiOauth': {'accessToken': 'ACCESS-A', 'refreshToken': 'REFRESH-A', 'subscriptionType': 'max'},
        'oauthAccount': {'accountUuid': 'UUID-A', 'emailAddress': 'a@example.com'},
    })
    _write(acc / 'backup.json', {
        'slot': 'backup', 'label': 'b@example.com', 'accountUuid': 'UUID-B',
        'subscriptionType': 'max', 'capturedAt': 't0',
        'claudeAiOauth': {'accessToken': 'ACCESS-B', 'refreshToken': 'REFRESH-B', 'subscriptionType': 'max'},
        'oauthAccount': {'accountUuid': 'UUID-B', 'emailAddress': 'b@example.com'},
    })
    return {'cred': cred, 'cfg': cfg, 'acc': acc}


def test_swap_switches_subscription_and_preserves_the_rest(f_env):
    host = _load(f_env['cred'])
    host['claudeAiOauth']['refreshToken'] = 'REFRESH-A-ROTATED'
    f_env['cred'].write_text(json.dumps(host))

    assert cli.main(['swap']) == 0

    cred = _load(f_env['cred'])
    assert cred['claudeAiOauth']['accessToken'] == 'ACCESS-B'
    assert cred['mcpOAuth']['gitlab']['access_token'] == 'MCP-SECRET'

    cfg = _load(f_env['cfg'])
    assert cfg['oauthAccount']['emailAddress'] == 'b@example.com'
    assert cfg['projects']['/x']['history'] == [1, 2, 3]
    assert cfg['numStartups'] == 42

    primary = _load(f_env['acc'] / 'primary.json')
    assert primary['claudeAiOauth']['refreshToken'] == 'REFRESH-A-ROTATED'


def test_status_marks_active_slot(f_env, capsys):
    assert cli.main(['status']) == 0
    assert '* primary' in capsys.readouterr().out


def test_swap_roundtrip_returns_to_original(f_env):
    cli.main(['swap'])
    cli.main(['swap'])
    assert _load(f_env['cred'])['claudeAiOauth']['accessToken'] == 'ACCESS-A'


def test_use_current_slot_is_noop(f_env, capsys):
    assert cli.main(['use', 'primary']) == 0
    assert 'already on' in capsys.readouterr().out


def test_snapshot_stores_current_host_account(f_env):
    assert cli.main(['snapshot', 'third']) == 0
    third = _load(f_env['acc'] / 'third.json')
    assert third['accountUuid'] == 'UUID-A'
    assert third['claudeAiOauth']['accessToken'] == 'ACCESS-A'


def test_swap_creates_a_backup(f_env):
    cli.main(['swap'])
    backups = f_env['acc'] / 'backups'
    assert backups.is_dir() and any(backups.iterdir())


def test_use_unknown_slot_errors(f_env, capsys):
    assert cli.main(['use', 'nope']) == 1
    assert 'not found' in capsys.readouterr().err


def test_status_no_slots(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('CLAUDE_CONFIG_FILE', str(tmp_path / 'nope.json'))
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(tmp_path / 'acc'))
    assert cli.main(['status']) == 0
    out = capsys.readouterr().out
    assert '<none>' in out
    assert '(none yet)' in out


def test_status_host_not_in_any_slot(f_env, capsys):
    cfg = _load(f_env['cfg'])
    cfg['oauthAccount']['accountUuid'] = 'UUID-UNKNOWN'
    f_env['cfg'].write_text(json.dumps(cfg))
    assert cli.main(['status']) == 0
    assert 'not captured in any slot' in capsys.readouterr().out


def test_snapshot_invalid_slot(f_env, capsys):
    assert cli.main(['snapshot', 'BAD NAME']) == 1
    assert 'usage' in capsys.readouterr().err


def test_snapshot_no_host_creds(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('CLAUDE_CRED_FILE', str(tmp_path / 'none.json'))
    monkeypatch.setenv('CLAUDE_CONFIG_FILE', str(tmp_path / 'cfg.json'))
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(tmp_path / 'acc'))
    assert cli.main(['snapshot', 'primary']) == 1
    assert 'no active credentials' in capsys.readouterr().err


def test_apply_invalid_slot_name(f_env, capsys):
    assert cli.main(['use', 'BAD NAME']) == 1
    assert 'invalid slot name' in capsys.readouterr().err


def test_apply_missing_config(tmp_path, monkeypatch, capsys):
    acc = tmp_path / 'acc'
    _write(acc / 'primary.json', {
        'slot': 'primary', 'accountUuid': 'X', 'label': 'x',
        'claudeAiOauth': {'accessToken': 'A'}, 'oauthAccount': {'accountUuid': 'X'},
    })
    monkeypatch.setenv('CLAUDE_CONFIG_FILE', str(tmp_path / 'missing.json'))
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(acc))
    assert cli.main(['use', 'primary']) == 1
    assert 'host config' in capsys.readouterr().err


def test_apply_warns_when_host_not_in_slot(f_env, capsys):
    cfg = _load(f_env['cfg'])
    cfg['oauthAccount']['accountUuid'] = 'UUID-C'
    f_env['cfg'].write_text(json.dumps(cfg))
    assert cli.main(['use', 'backup']) == 0
    assert "isn't in any slot" in capsys.readouterr().err
    assert (f_env['acc'] / '.last-active.json').exists()


def test_swap_needs_two_slots(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('CLAUDE_CONFIG_FILE', str(tmp_path / 'cfg.json'))
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(tmp_path / 'empty'))
    assert cli.main(['swap']) == 1
    assert 'needs 2' in capsys.readouterr().err


def test_swap_too_many_slots(f_env, capsys):
    _write(f_env['acc'] / 'third.json', {
        'slot': 'third', 'accountUuid': 'UUID-C', 'label': 'c',
        'claudeAiOauth': {}, 'oauthAccount': {},
    })
    assert cli.main(['swap']) == 1
    assert 'more than 2' in capsys.readouterr().err


def test_swap_host_matches_no_slot(f_env, capsys):
    cfg = _load(f_env['cfg'])
    cfg['oauthAccount']['accountUuid'] = 'UUID-C'
    f_env['cfg'].write_text(json.dumps(cfg))
    assert cli.main(['swap']) == 1
    assert 'matches no slot' in capsys.readouterr().err


def test_main_no_command_prints_help(capsys):
    assert cli.main([]) == 1
    assert 'usage' in capsys.readouterr().err.lower()


def test_main_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(['--version'])
    assert exc.value.code == 0
    assert '0.1.0' in capsys.readouterr().out


def test_main_aliases(f_env, capsys):
    assert cli.main(['st']) == 0
    assert cli.main(['save', 'primary']) == 0
    assert cli.main(['switch', 'primary']) == 0
    capsys.readouterr()
    assert cli.main(['toggle']) == 0


def test_prune_backups_keeps_10(tmp_path, monkeypatch):
    backups = tmp_path / 'acc' / 'backups'
    backups.mkdir(parents=True)
    for i in range(12):
        (backups / f'b{i:02d}').mkdir()
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(tmp_path / 'acc'))
    cli._prune_backups(keep=10)
    assert len(list(backups.iterdir())) == 10


def test_prune_backups_no_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_ACCOUNTS_DIR', str(tmp_path / 'nonexistent'))
    cli._prune_backups()


def test_atomic_write_cleans_temp_on_error(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('disk full')

    monkeypatch.setattr(cli.os, 'replace', boom)
    with pytest.raises(RuntimeError):
        cli._atomic_write_json(tmp_path / 'x.json', {'a': 1})
    assert not list(tmp_path.glob('.tmp.*'))


def test_capture_success(f_env, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, 'which', lambda name: '/usr/bin/claude')

    def fake_run(cmd, env=None, **kwargs):
        booth = Path(env['CLAUDE_CONFIG_DIR'])
        (booth / '.credentials.json').write_text(json.dumps(
            {'claudeAiOauth': {'accessToken': 'ACCESS-C', 'subscriptionType': 'max'}}))
        (booth / '.claude.json').write_text(json.dumps(
            {'oauthAccount': {'accountUuid': 'UUID-C', 'emailAddress': 'c@example.com'}}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cli.subprocess, 'run', fake_run)
    assert cli.main(['capture', 'third']) == 0
    slot = _load(f_env['acc'] / 'third.json')
    assert slot['accountUuid'] == 'UUID-C'
    assert slot['claudeAiOauth']['accessToken'] == 'ACCESS-C'
    assert 'captured' in capsys.readouterr().out


def test_capture_no_claude_cli(f_env, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, 'which', lambda name: None)
    assert cli.main(['capture', 'third']) == 1
    assert 'not found in PATH' in capsys.readouterr().err


def test_capture_login_not_completed(f_env, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, 'which', lambda name: '/usr/bin/claude')
    monkeypatch.setattr(cli.subprocess, 'run', lambda cmd, env=None, **k: subprocess.CompletedProcess(cmd, 1))
    assert cli.main(['capture', 'third']) == 1
    assert 'login not completed' in capsys.readouterr().err


def test_capture_invalid_slot(capsys):
    assert cli.main(['capture', 'BAD NAME']) == 1
    assert 'usage' in capsys.readouterr().err
