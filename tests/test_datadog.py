"""Tests for Datadog integration (no-op when DD_API_KEY unset)."""

from unittest.mock import patch, MagicMock

import pytest

from tor_exit_block import datadog


class TestDatadogNoOp:
    """When DD_API_KEY is not set, Datadog functions should not make HTTP requests."""

    def test_emit_fetcher_metrics_no_raise_when_unset(self):
        with patch.object(datadog, "DD_API_KEY", None):
            datadog.emit_fetcher_metrics(
                list_size=100,
                success=True,
                last_fetch_time_ms=1000.0,
            )

    def test_emit_block_event_no_raise_when_unset(self):
        with patch.object(datadog, "DD_API_KEY", None):
            datadog.emit_block_event(client_ip="1.2.3.4", path="/api/foo")

    def test_no_http_request_when_dd_api_key_unset(self):
        """When DD_API_KEY is None, _post returns without calling urlopen."""
        with patch.object(datadog, "DD_API_KEY", None):
            with patch("urllib.request.urlopen") as mock_urlopen:
                datadog.gauge("test_metric", 1.0)
                datadog.event("Test", "Text")
                mock_urlopen.assert_not_called()

    def test_http_request_when_dd_api_key_set(self):
        """When DD_API_KEY is set, _post calls urlopen."""
        with patch.object(datadog, "DD_API_KEY", "fake-key"):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp
                datadog.gauge("test_metric", 1.0)
                mock_urlopen.assert_called_once()

    def test_post_returns_false_on_exception(self):
        """When urlopen raises, _post catches, prints, and returns False."""
        with patch.object(datadog, "DD_API_KEY", "fake-key"):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.side_effect = OSError("Connection refused")
                out = datadog.gauge("test_metric", 1.0)
                assert out is False

    def test_emit_fetcher_metrics_failure_emits_event(self):
        """When success=False, emit_fetcher_metrics calls event() for the failure alert."""
        with patch.object(datadog, "DD_API_KEY", "fake-key"):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.status = 200
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_urlopen.return_value = mock_resp
                datadog.emit_fetcher_metrics(
                    list_size=0,
                    success=False,
                    last_fetch_time_ms=0.0,
                )
                # Should call urlopen for gauge (list_size, fetch_success, list_age_seconds) and event
                assert mock_urlopen.call_count >= 4
                # One of the calls should be to the events API
                urls = [getattr(c[0][0], "full_url", c[0][0]) for c in mock_urlopen.call_args_list]
                assert any("events" in str(u) for u in urls)
