"""Unit tests for sample.scripts.run_unihiker module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from sample.scripts.run_unihiker import _resolve_script_path, run_unihiker


class TestResolveScriptPath:
    """Tests for _resolve_script_path."""

    def test_returns_existing_script_path(self) -> None:
        path = _resolve_script_path()
        assert path.name == "run_unihiker.sh"
        assert path.exists()

    def test_raises_when_script_missing(self, tmp_path: Path) -> None:
        fake_py = tmp_path / "run_unihiker.py"
        fake_py.touch()
        import sample.scripts.run_unihiker as mod

        original = mod.__file__
        try:
            mod.__file__ = str(fake_py)
            with pytest.raises(FileNotFoundError, match="Shell script not found"):
                _resolve_script_path()
        finally:
            mod.__file__ = original


class TestRunUnihiker:
    """Tests for run_unihiker function."""

    @patch("sample.scripts.run_unihiker.subprocess.run")
    @patch("sample.scripts.run_unihiker._resolve_script_path")
    def test_default_args(
        self,
        mock_resolve: patch,
        mock_run: patch,
    ) -> None:
        mock_resolve.return_value = Path("/fake/run_unihiker.sh")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_unihiker()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/fake/run_unihiker.sh"
        assert "--log-dir" in cmd
        assert "/tmp/ble-key-agent" in cmd
        assert "--debug" not in cmd

    @patch("sample.scripts.run_unihiker.subprocess.run")
    @patch("sample.scripts.run_unihiker._resolve_script_path")
    def test_debug_flag(
        self,
        mock_resolve: patch,
        mock_run: patch,
    ) -> None:
        mock_resolve.return_value = Path("/fake/run_unihiker.sh")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_unihiker(debug=True)

        cmd = mock_run.call_args[0][0]
        assert "--debug" in cmd

    @patch("sample.scripts.run_unihiker.subprocess.run")
    @patch("sample.scripts.run_unihiker._resolve_script_path")
    def test_custom_log_dir(
        self,
        mock_resolve: patch,
        mock_run: patch,
    ) -> None:
        mock_resolve.return_value = Path("/fake/run_unihiker.sh")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_unihiker(log_dir="/custom/logs")

        cmd = mock_run.call_args[0][0]
        log_dir_idx = cmd.index("--log-dir")
        assert cmd[log_dir_idx + 1] == "/custom/logs"

    @patch("sample.scripts.run_unihiker.subprocess.run")
    @patch("sample.scripts.run_unihiker._resolve_script_path")
    def test_extra_args(
        self,
        mock_resolve: patch,
        mock_run: patch,
    ) -> None:
        mock_resolve.return_value = Path("/fake/run_unihiker.sh")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_unihiker(extra_args=["--device-name", "MyDevice"])

        cmd = mock_run.call_args[0][0]
        assert "--device-name" in cmd
        assert "MyDevice" in cmd

    @patch("sample.scripts.run_unihiker.subprocess.run")
    @patch("sample.scripts.run_unihiker._resolve_script_path")
    def test_check_true(
        self,
        mock_resolve: patch,
        mock_run: patch,
    ) -> None:
        mock_resolve.return_value = Path("/fake/run_unihiker.sh")
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        run_unihiker()

        assert mock_run.call_args[1]["check"] is True
