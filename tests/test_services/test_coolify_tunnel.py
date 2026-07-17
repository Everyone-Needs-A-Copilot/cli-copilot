"""Tests for the Coolify SSH tunnel manager.

The real tunnel spawns ``ssh -L`` as a subprocess. These tests mock
``subprocess.run`` and ``subprocess.Popen`` so they cover command construction,
ready-port waiting, error paths, and proper registry+process lifecycle without
opening real sockets.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from copilot_cli.services.coolify.core.exceptions import SSHError
from copilot_cli.services.coolify.core.tunnel import (
    _allocate_free_local_port,
    _resolve_container_ip,
    _wait_for_local_port,
    open_tunnel,
)
from copilot_cli.services.postgresql.safety import is_tunneled
from copilot_cli.services.postgresql.transfer import SSHTarget

SSH = SSHTarget(user="root", host="10.0.0.5", key_file="/keys/id")


class TestAllocateFreeLocalPort:
    def test_returns_valid_ephemeral_port(self):
        port = _allocate_free_local_port()
        assert 1024 < port < 65536


class TestResolveContainerIp:
    def test_happy_path(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="10.0.1.17\n", stderr=""
            ),
        ) as run:
            ip = _resolve_container_ip(SSH, "abc-uuid")
            cmd = run.call_args[0][0]
            assert cmd[0] == "ssh"
            assert "root@10.0.0.5" in cmd
            assert "docker inspect" in cmd[-1]
            assert "abc-uuid" in cmd[-1]
            assert "coolify.IPAddress" in cmd[-1]
        assert ip == "10.0.1.17"

    def test_custom_network(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout="172.20.0.4\n", stderr=""
            ),
        ) as run:
            _resolve_container_ip(SSH, "abc", network="bridge")
            assert "bridge.IPAddress" in run.call_args[0][0][-1]

    def test_inspect_nonzero_raises(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="no such container"
            ),
        ):
            with pytest.raises(SSHError, match="docker inspect failed"):
                _resolve_container_ip(SSH, "missing")

    def test_empty_ip_raises(self):
        # docker inspect returns empty string when the container is not on that network
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr=""),
        ):
            with pytest.raises(SSHError, match="has no IP on network"):
                _resolve_container_ip(SSH, "abc")


class TestWaitForLocalPort:
    def test_returns_when_port_accepts(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.stderr = MagicMock()
        mock_socket = MagicMock()
        mock_socket.__enter__ = MagicMock(return_value=mock_socket)
        mock_socket.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_socket):
            _wait_for_local_port(54321, proc, timeout=1.0)  # no raise

    def test_raises_when_proc_exits_early(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = 255
        proc.returncode = 255
        proc.stderr = MagicMock()
        proc.stderr.read.return_value = b"ssh: connect to host 10.0.0.5 port 22: Connection refused"
        with pytest.raises(SSHError, match="exited with code 255"):
            _wait_for_local_port(54321, proc, timeout=1.0)

    def test_raises_on_timeout(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.terminate = MagicMock()
        with patch("socket.create_connection", side_effect=OSError("refused")):
            with patch("time.sleep"):  # don't actually sleep
                with pytest.raises(SSHError, match="did not become ready"):
                    _wait_for_local_port(54321, proc, timeout=0.05)
        proc.terminate.assert_called_once()


class TestOpenTunnel:
    def test_registers_url_inside_context_unregisters_after(self, monkeypatch):
        # _resolve_container_ip
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._resolve_container_ip",
            lambda *_a, **_kw: "10.0.1.17",
        )
        # _allocate_free_local_port — fixed port for assertion
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._allocate_free_local_port",
            lambda: 54321,
        )
        # _wait_for_local_port — instant success
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._wait_for_local_port",
            lambda *_a, **_kw: None,
        )
        # subprocess.Popen — capture command + lifecycle
        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.wait.return_value = 0
        with patch("subprocess.Popen", return_value=fake_proc) as popen:
            with open_tunnel(
                ssh=SSH,
                container="abc-uuid",
                db_user="u",
                db_password="p@ss/word",
                db_name="d",
            ) as url:
                # URL points at our fixed port and contains URL-quoted creds.
                assert url.startswith("postgresql://u:p%40ss%2Fword@127.0.0.1:54321/")
                # The URL is registered as tunneled during the context.
                assert is_tunneled(url) is True

                # Popen got the right ssh -L args.
                cmd = popen.call_args[0][0]
                assert "-L" in cmd
                assert "127.0.0.1:54321:10.0.1.17:5432" in cmd
                assert "-N" in cmd

            # After exit: unregistered AND proc terminated.
            assert is_tunneled(url) is False
            fake_proc.terminate.assert_called()

    def test_failure_during_setup_still_terminates_proc(self, monkeypatch):
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._resolve_container_ip",
            lambda *_a, **_kw: "10.0.1.17",
        )
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._allocate_free_local_port",
            lambda: 54321,
        )
        # _wait_for_local_port blows up: tunnel never became ready.
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._wait_for_local_port",
            MagicMock(side_effect=SSHError("nope")),
        )
        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.wait.return_value = 0
        with patch("subprocess.Popen", return_value=fake_proc):
            with pytest.raises(SSHError, match="nope"):
                with open_tunnel(
                    ssh=SSH,
                    container="abc",
                    db_user="u",
                    db_password="p",
                    db_name="d",
                ):
                    pass  # pragma: no cover
        fake_proc.terminate.assert_called()

    def test_missing_container_raises(self):
        from copilot_cli.services.coolify.core.exceptions import ConfigError

        with pytest.raises(ConfigError, match="container is required"):
            with open_tunnel(
                ssh=SSH,
                container="",
                db_user="u",
                db_password="p",
                db_name="d",
            ):
                pass  # pragma: no cover

    def test_unregister_runs_even_if_body_raises(self, monkeypatch):
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._resolve_container_ip",
            lambda *_a, **_kw: "10.0.1.17",
        )
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._allocate_free_local_port",
            lambda: 54321,
        )
        monkeypatch.setattr(
            "copilot_cli.services.coolify.core.tunnel._wait_for_local_port",
            lambda *_a, **_kw: None,
        )
        fake_proc = MagicMock(spec=subprocess.Popen)
        captured_url: list[str] = []
        with patch("subprocess.Popen", return_value=fake_proc):
            with pytest.raises(RuntimeError, match="boom"):
                with open_tunnel(
                    ssh=SSH,
                    container="abc",
                    db_user="u",
                    db_password="p",
                    db_name="d",
                ) as url:
                    captured_url.append(url)
                    raise RuntimeError("boom")
        assert is_tunneled(captured_url[0]) is False
