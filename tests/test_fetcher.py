"""Tests for fetcher."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tor_exit_block.fetcher import run_fetcher, main


class TestRunFetcher:
    def test_success_writes_file_and_emits_metrics(self):
        with patch("tor_exit_block.fetcher.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.text = "192.168.1.1\n10.0.0.1\n"
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            with patch("tor_exit_block.fetcher.emit_fetcher_metrics") as mock_metrics:
                with tempfile.TemporaryDirectory() as tmp:
                    run_fetcher(output_dir=tmp)

                    output_file = Path(tmp) / "tor-exit-nodes.txt"
                    assert output_file.exists()
                    content = output_file.read_text()
                    lines = [line for line in content.strip().split("\n") if line]
                    assert set(lines) == {"192.168.1.1", "10.0.0.1"}

                    last_fetch = Path(tmp) / ".last-fetch-time"
                    assert last_fetch.exists()
                    assert int(last_fetch.read_text().strip()) > 0

                    mock_metrics.assert_called_once()
                    call_kw = mock_metrics.call_args[1]
                    assert call_kw["list_size"] == 2
                    assert call_kw["success"] is True
                    assert call_kw["last_fetch_time_ms"] > 0

    def test_failure_keeps_previous_file_and_emits_failure_metrics(self):
        with patch("tor_exit_block.fetcher.requests") as mock_requests:
            mock_requests.get.side_effect = Exception("Network error")

            with patch("tor_exit_block.fetcher.emit_fetcher_metrics") as mock_metrics:
                with tempfile.TemporaryDirectory() as tmp:
                    prev_file = Path(tmp) / "tor-exit-nodes.txt"
                    prev_file.write_text("1.2.3.4\n")
                    last_fetch = Path(tmp) / ".last-fetch-time"
                    last_fetch.write_text("999000000000")

                    run_fetcher(output_dir=tmp)

                    assert prev_file.read_text().strip() == "1.2.3.4"
                    mock_metrics.assert_called_once()
                    call_kw = mock_metrics.call_args[1]
                    assert call_kw["success"] is False
                    assert call_kw["list_size"] == 0
                    assert call_kw["last_fetch_time_ms"] == 999000000000.0

    def test_http_error_does_not_overwrite_file(self):
        with patch("tor_exit_block.fetcher.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = Exception("403 Forbidden")
            mock_requests.get.return_value = mock_resp

            with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                with tempfile.TemporaryDirectory() as tmp:
                    prev_file = Path(tmp) / "tor-exit-nodes.txt"
                    prev_file.write_text("1.2.3.4\n")
                    last_fetch = Path(tmp) / ".last-fetch-time"
                    last_fetch.write_text("999000000000")

                    run_fetcher(output_dir=tmp)

                    assert prev_file.read_text().strip() == "1.2.3.4"

    def test_creates_output_directory(self):
        with patch("tor_exit_block.fetcher.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.text = "10.0.0.1\n"
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            with patch("tor_exit_block.fetcher.emit_fetcher_metrics"):
                with tempfile.TemporaryDirectory() as tmp:
                    out_dir = os.path.join(tmp, "subdir", "data")
                    run_fetcher(output_dir=out_dir)

                    assert os.path.isdir(out_dir)
                    output_file = Path(out_dir) / "tor-exit-nodes.txt"
                    assert output_file.exists()
                    assert "10.0.0.1" in output_file.read_text()

    def test_failure_with_invalid_last_fetch_file_does_not_raise(self):
        """When fetch fails and .last-fetch-time exists but is unreadable/invalid, run_fetcher still completes."""
        with patch("tor_exit_block.fetcher.requests") as mock_requests:
            mock_requests.get.side_effect = Exception("Network error")

            with patch("tor_exit_block.fetcher.emit_fetcher_metrics") as mock_metrics:
                with tempfile.TemporaryDirectory() as tmp:
                    last_fetch = Path(tmp) / ".last-fetch-time"
                    last_fetch.write_text("not-a-number")

                    run_fetcher(output_dir=tmp)

                    mock_metrics.assert_called_once()
                    call_kw = mock_metrics.call_args[1]
                    assert call_kw["success"] is False
                    assert call_kw["list_size"] == 0

    def test_main_calls_run_fetcher_and_exits_zero(self):
        """main() invokes run_fetcher and exits with 0."""
        with patch("tor_exit_block.fetcher.run_fetcher") as mock_run:
            with patch.object(sys, "exit") as mock_exit:
                main()
                mock_run.assert_called_once()
                mock_exit.assert_called_once_with(0)
