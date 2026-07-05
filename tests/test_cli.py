import json
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
