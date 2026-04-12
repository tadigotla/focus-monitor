"""Smoke tests for the `tmp_home` fixture itself.

These verify that the fixture actually rebinds every captured config path,
not just the `focusmonitor.config` module attributes. If a new module
starts importing a config path by value, one of these tests should fail
and remind the maintainer to add it to `_REBIND_TARGETS` in conftest.py.
"""

from __future__ import annotations

import socket

import pytest

from focusmonitor import config as config_mod


def test_tmp_home_moves_config_dir(tmp_home):
    assert config_mod.CONFIG_DIR == tmp_home
    assert config_mod.CONFIG_DIR.exists()


def test_tmp_home_moves_db_path(tmp_home):
    assert str(config_mod.DB_PATH).startswith(str(tmp_home))
    assert config_mod.DB_PATH.name == "activity.db"


def test_tmp_home_moves_screenshot_dir(tmp_home):
    assert str(config_mod.SCREENSHOT_DIR).startswith(str(tmp_home))
    assert config_mod.SCREENSHOT_DIR.exists()


def test_tmp_home_rebinds_screenshots_module(tmp_home):
    """`focusmonitor.screenshots` imported SCREENSHOT_DIR by value."""
    from focusmonitor import screenshots as sm
    assert sm.SCREENSHOT_DIR == config_mod.SCREENSHOT_DIR


def test_tmp_home_rebinds_db_module(tmp_home):
    from focusmonitor import db as db_mod
    assert db_mod.DB_PATH == config_mod.DB_PATH


def test_tmp_home_rebinds_cleanup_module(tmp_home):
    from focusmonitor import cleanup as cu
    assert cu.LOG_DIR == config_mod.LOG_DIR


def test_tmp_home_rebinds_dashboard_module(tmp_home):
    from focusmonitor import dashboard as dash
    assert dash.DB_PATH == config_mod.DB_PATH
    assert dash.DISCOVERED_FILE == config_mod.DISCOVERED_FILE


def test_tmp_home_rebinds_tasks_module(tmp_home):
    from focusmonitor import tasks as t
    assert t.TASKS_JSON_FILE == config_mod.TASKS_JSON_FILE
    assert t.DISCOVERED_FILE == config_mod.DISCOVERED_FILE


def test_two_tests_do_not_share_state(tmp_home):
    """First half of a paired test: write a sentinel file."""
    (config_mod.TASKS_JSON_FILE).write_text('["sentinel"]')
    assert config_mod.TASKS_JSON_FILE.exists()


def test_two_tests_do_not_share_state_check(tmp_home):
    """Second half: a fresh tmp_home must not see the previous write."""
    assert not config_mod.TASKS_JSON_FILE.exists()


def test_pytest_socket_blocks_external_connect():
    """pytest-socket must be actively blocking non-loopback sockets.

    Both `SocketBlockedError` (socket() creation) and
    `SocketConnectBlockedError` (connect()) are pytest-socket's own
    exceptions — neither subclasses OSError, so we catch them explicitly.
    """
    from pytest_socket import SocketBlockedError, SocketConnectBlockedError
    with pytest.raises((SocketBlockedError, SocketConnectBlockedError)):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.1)
        s.connect(("203.0.113.1", 80))  # TEST-NET-3, never routable
        s.close()
