from contextlib import contextmanager

import arqparse.core.auth as auth_module


def test_is_network_error_distinguishes_http_errors():
    assert auth_module.is_network_error("Нет соединения с сервером: timeout") is True
    assert auth_module.is_network_error("HTTP 401: unauthorized") is False
    assert auth_module.is_network_error("Не авторизован. Войдите в аккаунт.") is False


def test_push_updates_via_xray_proxy_sends_both_payloads(monkeypatch):
    calls = []

    monkeypatch.setattr(
        auth_module,
        "get_session",
        lambda: {
            "user_id": "user-1",
            "token": "token-1",
            "server": "https://example.test",
        },
    )

    @contextmanager
    def fake_proxy(_proxy_config, _xray_path):
        yield {"http": "socks5h://127.0.0.1:20000", "https": "socks5h://127.0.0.1:20000"}

    def fake_request(server, method, path, data=None, headers=None, proxies=None, timeout=15):
        calls.append((server, method, path, data, headers, proxies, timeout))
        return {}

    monkeypatch.setattr(auth_module, "temporary_socks_proxy", fake_proxy)
    monkeypatch.setattr(auth_module, "_request_with_requests", fake_request)

    updated = auth_module.push_updates_via_xray_proxy(
        proxy_config="vless://test",
        xray_path="/tmp/xray",
        vpn_content="vpn-data",
        mtproto_content="mt-data",
    )

    assert updated == ["VPN", "MTProto"]
    assert len(calls) == 2
    assert calls[0][2] == "/api/sub/user-1"
    assert calls[0][3] == {"content": "vpn-data"}
    assert calls[1][2] == "/api/mtproto/user-1"
    assert calls[1][3] == {"content": "mt-data"}
    assert calls[0][4]["Authorization"] == "Bearer token-1"
    assert calls[0][5]["http"].startswith("socks5h://127.0.0.1:")


def test_normalize_server_url_requires_https():
    assert auth_module._normalize_server_url("https://example.test:9000/") == "https://example.test:9000"

    try:
        auth_module._normalize_server_url("http://example.test")
    except auth_module.AuthError as exc:
        assert "HTTPS" in str(exc)
    else:
        assert False, "Expected AuthError for non-HTTPS server URL"


def test_request_uses_pinned_fingerprint_on_tls_failure(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    def fake_request(**kwargs):
        calls.append(kwargs)
        if kwargs["verify"] is True:
            raise auth_module.requests.exceptions.SSLError("bad cert")
        return FakeResponse()

    monkeypatch.setattr(auth_module.requests, "request", fake_request)
    monkeypatch.setattr(auth_module, "_get_pinned_fingerprint", lambda _server=None: "a" * 64)
    monkeypatch.setattr(auth_module, "get_server_certificate_sha256", lambda _server: "a" * 64)

    result = auth_module._request_with_requests("https://example.test", "GET", "/health")

    assert result == {}
    assert len(calls) == 2
    assert calls[0]["verify"] is True
    assert calls[1]["verify"] is False
