import pytest
from tor_exit_block.parser import parse_tor_exit_list, is_valid_ip


class TestIsValidIp:
    def test_accepts_valid_ipv4(self):
        assert is_valid_ip("192.168.1.1") is True
        assert is_valid_ip("0.0.0.0") is True

    def test_accepts_valid_ipv6(self):
        assert is_valid_ip("2001:db8::1") is True
        assert is_valid_ip("::1") is True

    def test_rejects_invalid(self):
        assert is_valid_ip("") is False
        assert is_valid_ip("256.1.1.1") is False
        assert is_valid_ip("not-an-ip") is False


class TestParseTorExitList:
    def test_parses_one_ip_per_line(self):
        body = "192.168.1.1\n10.0.0.1\n"
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "192.168.1.1" in result
        assert "10.0.0.1" in result

    def test_skips_blank_and_invalid(self):
        body = "192.168.1.1\n\n# comment\n10.0.0.1\ninvalid\n"
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "192.168.1.1" in result
        assert "10.0.0.1" in result

    def test_parses_ipv6(self):
        body = "2001:db8::1\n::1\n"
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "2001:db8::1" in result
        assert "::1" in result

    def test_empty_body_returns_empty_set(self):
        assert parse_tor_exit_list("") == set()
        assert parse_tor_exit_list("\n\n\n") == set()

    def test_windows_line_endings(self):
        body = "192.168.1.1\r\n10.0.0.1\r\n"
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "192.168.1.1" in result
        assert "10.0.0.1" in result

    def test_deduplicates_ips(self):
        body = "192.168.1.1\n192.168.1.1\n10.0.0.1\n"
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "192.168.1.1" in result
        assert "10.0.0.1" in result

    def test_only_invalid_lines_returns_empty_set(self):
        body = "invalid\n256.1.1.1\nnope\n"
        result = parse_tor_exit_list(body)
        assert result == set()

    def test_strips_whitespace(self):
        body = "  192.168.1.1  \n  10.0.0.1  "
        result = parse_tor_exit_list(body)
        assert len(result) == 2
        assert "192.168.1.1" in result
        assert "10.0.0.1" in result
