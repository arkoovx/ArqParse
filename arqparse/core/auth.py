"""
Модуль авторизации arqParse.
Взаимодействие с сервером подписок.
"""

import os
import json
import socket
import ssl
import tempfile
import hashlib
from urllib.parse import urlparse

import requests
import urllib3

from arqparse.core.xray_tester_simple import temporary_socks_proxy

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Адрес сервера по умолчанию
DEFAULT_SERVER = "https://194.87.54.75:9000"

# Путь к локальной сессии
try:
    from kivy.utils import platform
except ImportError:
    platform = "linux"

if platform == 'android':
    from android.storage import app_storage_path
    SESSION_DIR = os.path.join(app_storage_path(), ".arqparse")
else:
    SESSION_DIR = os.path.expanduser("~/.arqparse")

SESSION_FILE = os.path.join(SESSION_DIR, "session.json")


class AuthError(Exception):
    """Ошибка авторизации/регистрации."""
    pass


def _normalize_server_url(server: str) -> str:
    """Проверяет и нормализует URL сервера подписок."""
    if not server or not isinstance(server, str):
        raise AuthError("Некорректный адрес сервера подписок")

    parsed = urlparse(server)
    if parsed.scheme != "https":
        raise AuthError("Сервер подписок должен использовать HTTPS")
    if not parsed.hostname:
        raise AuthError("У сервера подписок отсутствует host")
    return server.rstrip("/")


def _normalize_fingerprint(value: str) -> str:
    """Нормализует SHA-256 fingerprint сертификата."""
    if not value:
        return ""
    normalized = value.strip().lower().replace("sha256:", "").replace(":", "").replace(" ", "")
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise AuthError("Некорректный SHA-256 fingerprint сертификата")
    return normalized


def _get_pinned_fingerprint(server: str = None) -> str:
    """Возвращает настроенный fingerprint сервера из env или локальной сессии."""
    env_fp = os.environ.get("ARQPARSE_SERVER_CERT_SHA256", "").strip()
    if env_fp:
        return _normalize_fingerprint(env_fp)

    session = get_session()
    if session:
        session_server = session.get("server")
        session_fp = session.get("server_cert_sha256", "")
        if session_fp and (server is None or session_server == server):
            return _normalize_fingerprint(session_fp)

    return ""


def get_server_certificate_sha256(server: str) -> str:
    """Получает SHA-256 fingerprint TLS-сертификата сервера."""
    normalized_server = _normalize_server_url(server)
    parsed = urlparse(normalized_server)
    host = parsed.hostname
    port = parsed.port or 443

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert_bin = ssock.getpeercert(binary_form=True)
    except OSError as e:
        raise AuthError(f"Не удалось получить сертификат сервера: {e}")

    if not cert_bin:
        raise AuthError("Сервер не предоставил TLS-сертификат")

    return hashlib.sha256(cert_bin).hexdigest()


def _request_with_pinned_certificate(server: str, method: str, path: str, data: dict = None,
                                     headers: dict = None, proxies: dict = None,
                                     timeout: int = 15, fingerprint: str = "") -> dict:
    """Резервный запрос через pinned fingerprint при недоверенном сертификате."""
    normalized_server = _normalize_server_url(server)
    pinned = _normalize_fingerprint(fingerprint)
    actual = get_server_certificate_sha256(normalized_server)
    if actual != pinned:
        raise AuthError(
            "Fingerprint TLS-сертификата сервера не совпадает. "
            f"Ожидался {pinned}, получен {actual}"
        )

    url = f"{normalized_server}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    try:
        resp = requests.request(
            method=method,
            url=url,
            json=data,
            headers=req_headers,
            timeout=timeout,
            verify=False,
            proxies=proxies,
        )
    except requests.RequestException as e:
        raise AuthError(f"Нет соединения с сервером: {e}")

    if resp.status_code >= 400:
        try:
            err_json = resp.json()
            msg = err_json.get("detail", resp.text)
        except ValueError:
            msg = resp.text
        raise AuthError(f"HTTP {resp.status_code}: {msg}")

    if not resp.text:
        return {}

    try:
        return resp.json()
    except ValueError:
        return {}


def _get_tls_verify_config():
    """Возвращает настройки TLS-проверки для requests."""
    ca_bundle = os.environ.get("ARQPARSE_CA_BUNDLE", "").strip()
    if ca_bundle:
        if not os.path.exists(ca_bundle):
            raise AuthError(f"Файл CA bundle не найден: {ca_bundle}")
        return ca_bundle

    allow_insecure = os.environ.get("ARQPARSE_INSECURE_SSL", "").strip().lower()
    if allow_insecure in {"1", "true", "yes", "on"}:
        return False

    return True


def is_network_error(exc_or_message) -> bool:
    """Пытается отличить сетевой сбой от валидного ответа сервера с ошибкой."""
    msg = str(exc_or_message)
    if msg.startswith("HTTP "):
        return False
    if "Не авторизован" in msg or "Не указан user_id" in msg:
        return False
    return True


def _request(server: str, method: str, path: str, data: dict = None,
             headers: dict = None) -> dict:
    """Отправляет HTTP-запрос на сервер."""
    return _request_with_requests(server, method, path, data=data, headers=headers)


def _request_with_requests(server: str, method: str, path: str, data: dict = None,
                           headers: dict = None, proxies: dict = None,
                           timeout: int = 15) -> dict:
    """Отправляет HTTP-запрос через requests; умеет работать через SOCKS-прокси."""
    normalized_server = _normalize_server_url(server)
    url = f"{normalized_server}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    try:
        verify = _get_tls_verify_config()
        resp = requests.request(
            method=method,
            url=url,
            json=data,
            headers=req_headers,
            timeout=timeout,
            verify=verify,
            proxies=proxies,
        )
    except requests.exceptions.SSLError as e:
        pinned_fp = _get_pinned_fingerprint(normalized_server)
        if pinned_fp:
            return _request_with_pinned_certificate(
                normalized_server,
                method,
                path,
                data=data,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
                fingerprint=pinned_fp,
            )
        try:
            actual_fp = get_server_certificate_sha256(normalized_server)
            fp_hint = f" Текущий SHA-256 fingerprint сервера: {actual_fp}"
        except AuthError:
            fp_hint = ""
        raise AuthError(
            "TLS-проверка сервера не пройдена. "
            "Укажите доверенный CA через ARQPARSE_CA_BUNDLE, "
            "или задайте pinned fingerprint через ARQPARSE_SERVER_CERT_SHA256, "
            "или временно разрешите небезопасный режим через ARQPARSE_INSECURE_SSL=1. "
            f"Детали: {e}.{fp_hint}"
        )
    except requests.RequestException as e:
        raise AuthError(f"Нет соединения с сервером: {e}")
    except AuthError:
        raise

    if resp.status_code >= 400:
        try:
            err_json = resp.json()
            msg = err_json.get("detail", resp.text)
        except ValueError:
            msg = resp.text
        raise AuthError(f"HTTP {resp.status_code}: {msg}")

    if not resp.text:
        return {}

    try:
        return resp.json()
    except ValueError:
        return {}


def register(username: str, password: str, server: str = DEFAULT_SERVER) -> dict:
    """
    Регистрация нового пользователя.

    Returns:
        {"user_id": str, "token": str, "username": str, "sub_url": str}
    """
    result = _request(server, "POST", "/api/register", {
        "username": username,
        "password": password,
    })
    _save_session(result, server)
    return result


def login(username: str, password: str, server: str = DEFAULT_SERVER) -> dict:
    """
    Вход в аккаунт.

    Returns:
        {"user_id": str, "token": str, "username": str, "sub_url": str}
    """
    result = _request(server, "POST", "/api/login", {
        "username": username,
        "password": password,
    })
    _save_session(result, server)
    return result


def update_subscription(content: str, server: str = None) -> dict:
    """
    Обновить VPN подписку (all_top_vpn — Обход + Обычные).
    """
    session = get_session()
    if not session:
        raise AuthError("Не авторизован. Войдите в аккаунт.")

    srv = server or session.get("server", DEFAULT_SERVER)
    user_id = session["user_id"]
    token = session["token"]

    result = _request(srv, "POST", f"/api/sub/{user_id}", {
        "content": content,
    }, headers={
        "Authorization": f"Bearer {token}",
    })
    return result


def update_mtproto(content: str, server: str = None) -> dict:
    """
    Обновить MTProto подписку.
    """
    session = get_session()
    if not session:
        raise AuthError("Не авторизован. Войдите в аккаунт.")

    srv = server or session.get("server", DEFAULT_SERVER)
    user_id = session["user_id"]
    token = session["token"]

    result = _request(srv, "POST", f"/api/mtproto/{user_id}", {
        "content": content,
    }, headers={
        "Authorization": f"Bearer {token}",
    })
    return result


def push_updates_via_xray_proxy(proxy_config: str, xray_path: str,
                                vpn_content: str = "", mtproto_content: str = "",
                                server: str = None) -> list[str]:
    """Обновляет подписки через временный локальный SOCKS-прокси на базе рабочего VPN-конфига."""
    session = get_session()
    if not session:
        raise AuthError("Не авторизован. Войдите в аккаунт.")

    if not proxy_config:
        raise AuthError("Нет рабочего VPN-конфига для проксированного обновления")
    if not vpn_content and not mtproto_content:
        raise AuthError("Нет данных для отправки")

    srv = _normalize_server_url(server or session.get("server", DEFAULT_SERVER))
    user_id = session["user_id"]
    token = session["token"]
    req_headers = {"Authorization": f"Bearer {token}"}
    updated = []

    with temporary_socks_proxy(proxy_config, xray_path) as proxies:
        if vpn_content:
            _request_with_requests(
                srv,
                "POST",
                f"/api/sub/{user_id}",
                {"content": vpn_content},
                headers=req_headers,
                proxies=proxies,
            )
            updated.append("VPN")

        if mtproto_content:
            _request_with_requests(
                srv,
                "POST",
                f"/api/mtproto/{user_id}",
                {"content": mtproto_content},
                headers=req_headers,
                proxies=proxies,
            )
            updated.append("MTProto")

    return updated


def get_mtproto(user_id: str = None, server: str = None) -> str:
    """
    Получить MTProto конфиги.
    """
    session = get_session()
    srv = _normalize_server_url(server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER))
    uid = user_id or (session["user_id"] if session else None)

    if not uid:
        raise AuthError("Не указан user_id")

    url = f"{srv}/api/mtproto/{uid}"
    try:
        resp = requests.get(url, timeout=10, verify=_get_tls_verify_config())
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError as e:
        raise AuthError(
            "TLS-проверка сервера не пройдена. "
            "Укажите доверенный CA через ARQPARSE_CA_BUNDLE "
            "или временно разрешите небезопасный режим через ARQPARSE_INSECURE_SSL=1. "
            f"Детали: {e}"
        )
    except requests.RequestException as e:
        raise AuthError(f"Нет соединения с сервером: {e}")


def get_subscription(user_id: str = None, server: str = None) -> str:
    """
    Получить текст подписки.

    Args:
        user_id: ID пользователя (если None — берётся из сессии)
        server: Адрес сервера (если None — берётся из сессии)

    Returns:
        Текст подписки
    """
    session = get_session()
    srv = _normalize_server_url(server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER))
    uid = user_id or (session["user_id"] if session else None)

    if not uid:
        raise AuthError("Не указан user_id")

    url = f"{srv}/api/sub/{uid}"
    try:
        resp = requests.get(url, timeout=10, verify=_get_tls_verify_config())
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.SSLError as e:
        raise AuthError(
            "TLS-проверка сервера не пройдена. "
            "Укажите доверенный CA через ARQPARSE_CA_BUNDLE "
            "или временно разрешите небезопасный режим через ARQPARSE_INSECURE_SSL=1. "
            f"Детали: {e}"
        )
    except requests.RequestException as e:
        raise AuthError(f"Нет соединения с сервером: {e}")


def get_sub_url(user_id: str = None, server: str = None) -> str:
    """Возвращает публичную ссылку на подписку."""
    session = get_session()
    srv = _normalize_server_url(server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER))
    uid = user_id or (session["user_id"] if session else None)
    if not uid:
        raise AuthError("Не указан user_id")
    return f"{srv}/api/sub/{uid}"


# ─── Управление сессией ────────────────────────────────────────

def _save_session(data: dict, server: str):
    """Сохраняет сессию локально."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    normalized_server = _normalize_server_url(server)
    session = {
        "user_id": data["user_id"],
        "token": data["token"],
        "username": data["username"],
        "server": normalized_server,
    }
    pinned_fp = _get_pinned_fingerprint(normalized_server)
    if pinned_fp:
        session["server_cert_sha256"] = pinned_fp
    fd, tmp_path = tempfile.mkstemp(prefix="session_", suffix=".json", dir=SESSION_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SESSION_FILE)
        try:
            os.chmod(SESSION_FILE, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def get_session() -> dict:
    """Загружает текущую сессию. None если не авторизован."""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def clear_session():
    """Удаляет локальную сессию (выход из аккаунта)."""
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)


def is_logged_in() -> bool:
    """Проверяет, авторизован ли пользователь."""
    return get_session() is not None


def check_server(server: str = DEFAULT_SERVER) -> bool:
    """Проверяет доступность сервера."""
    try:
        _request(server, "GET", "/health")
        return True
    except AuthError:
        return False
