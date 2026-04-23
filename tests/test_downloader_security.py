import requests

from arqparse.core.downloader import _download_text_response, validate_download_url


def test_validate_download_url_allows_public_https():
    validate_download_url("https://raw.githubusercontent.com/test/file.txt")


def test_validate_download_url_rejects_http_and_private_hosts():
    for url in [
        "http://example.com/file.txt",
        "https://127.0.0.1/file.txt",
        "https://localhost/file.txt",
        "https://10.0.0.1/file.txt",
    ]:
        try:
            validate_download_url(url)
        except ValueError:
            pass
        else:
            assert False, f"Expected validation error for {url}"


def test_download_text_response_rejects_oversized_payload():
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/plain"}

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536, decode_unicode=False):
            yield b"a" * (11 * 1024 * 1024)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    try:
        _download_text_response(FakeSession(), "https://example.test/file.txt")
    except requests.exceptions.RequestException as exc:
        assert "слишком большой" in str(exc)
    else:
        assert False, "Expected oversized payload rejection"
