"""
Модуль авторизации arqParse.
Взаимодействие с сервером подписок.
"""

import os
import json
import urllib.request
import urllib.error

# Адрес сервера по умолчанию
DEFAULT_SERVER = "https://194.87.54.75:9000"

# Путь к локальной сессии
SESSION_DIR = os.path.expanduser("~/.arqparse")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")


class AuthError(Exception):
    """Ошибка авторизации/регистрации."""
    pass


def _request(server: str, method: str, path: str, data: dict = None,
             headers: dict = None) -> dict:
    """Отправляет HTTP-запрос на сервер."""
    url = f"{server}{path}"
    body = None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

    # Отключаем проверку SSL (т.к. self-signed сертификат IP)
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            if resp.status == 200 and raw:
                return json.loads(raw)
            return {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("detail", str(err_body))
        except json.JSONDecodeError:
            msg = err_body
        # Добавляем HTTP статус для большей информативности
        raise AuthError(f"HTTP {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise AuthError(f"Нет соединения с сервером: {e.reason}")
    except Exception as e:
        raise AuthError(str(e))


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


def get_mtproto(user_id: str = None, server: str = None) -> str:
    """
    Получить MTProto конфиги.
    """
    session = get_session()
    srv = server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER)
    uid = user_id or (session["user_id"] if session else None)

    if not uid:
        raise AuthError("Не указан user_id")

    url = f"{srv}/api/mtproto/{uid}"
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return resp.read().decode("utf-8")


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
    srv = server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER)
    uid = user_id or (session["user_id"] if session else None)

    if not uid:
        raise AuthError("Не указан user_id")

    url = f"{srv}/api/sub/{uid}"
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return resp.read().decode("utf-8")


def get_sub_url(user_id: str = None, server: str = None) -> str:
    """Возвращает публичную ссылку на подписку."""
    session = get_session()
    srv = server or (session.get("server", DEFAULT_SERVER) if session else DEFAULT_SERVER)
    uid = user_id or (session["user_id"] if session else None)
    if not uid:
        raise AuthError("Не указан user_id")
    return f"{srv}/api/sub/{uid}"


# ─── Управление сессией ────────────────────────────────────────

def _save_session(data: dict, server: str):
    """Сохраняет сессию локально."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    session = {
        "user_id": data["user_id"],
        "token": data["token"],
        "username": data["username"],
        "server": server,
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2)
    # Права только для владельца
    os.chmod(SESSION_FILE, 0o600)


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
