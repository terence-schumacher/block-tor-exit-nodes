import pytest
from tor_exit_block.client_ip import get_client_ip, ClientIpOptions


class TestGetClientIp:
    def test_uses_remote_addr_when_no_headers(self):
        environ = {"REMOTE_ADDR": "1.2.3.4"}
        assert get_client_ip(environ) == "1.2.3.4"

    def test_uses_x_real_ip_when_present(self):
        environ = {"REMOTE_ADDR": "1.2.3.4", "HTTP_X_REAL_IP": "10.0.0.1"}
        assert get_client_ip(environ) == "10.0.0.1"

    def test_uses_rightmost_x_forwarded_for_with_trusted_1(self):
        environ = {
            "REMOTE_ADDR": "1.2.3.4",
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 172.16.0.1",
        }
        assert get_client_ip(environ, options=ClientIpOptions(trusted_proxy_count=1)) == "10.0.0.1"

    def test_uses_rightmost_when_trusted_0(self):
        environ = {"HTTP_X_FORWARDED_FOR": "10.0.0.1, 172.16.0.1"}
        assert (
            get_client_ip(environ, options=ClientIpOptions(trusted_proxy_count=0)) == "172.16.0.1"
        )

    def test_empty_remote_addr_returns_empty_string(self):
        environ = {}
        assert get_client_ip(environ) == ""

    def test_single_x_forwarded_for_value(self):
        environ = {"HTTP_X_FORWARDED_FOR": "10.0.0.1", "REMOTE_ADDR": "1.2.3.4"}
        assert get_client_ip(environ, options=ClientIpOptions(trusted_proxy_count=1)) == "10.0.0.1"

    def test_custom_forwarded_for_header_name(self):
        opts = ClientIpOptions(forwarded_for_header="x-real-ip")
        environ = {"HTTP_X_REAL_IP": "10.0.0.1", "REMOTE_ADDR": "1.2.3.4"}
        assert get_client_ip(environ, options=opts) == "10.0.0.1"

    def test_three_proxies_trusted_2_returns_client(self):
        environ = {"HTTP_X_FORWARDED_FOR": "10.0.0.1, 172.16.0.1, 192.168.1.1"}
        assert get_client_ip(environ, options=ClientIpOptions(trusted_proxy_count=2)) == "10.0.0.1"

    def test_no_environ_uses_headers_and_remote_addr(self):
        """When environ is None, headers and remote_addr are used (e.g. from a non-WSGI context)."""
        assert (
            get_client_ip(
                environ=None,
                headers={"x-forwarded-for": "10.0.0.1, 172.16.0.1"},
                remote_addr="172.16.0.1",
                options=ClientIpOptions(trusted_proxy_count=1),
            )
            == "10.0.0.1"
        )

    def test_no_environ_remote_addr_only(self):
        """When environ is None and no forwarded header, returns remote_addr or empty."""
        assert get_client_ip(environ=None, headers={}, remote_addr="5.6.7.8") == "5.6.7.8"
        assert get_client_ip(environ=None, headers=None, remote_addr=None) == ""
