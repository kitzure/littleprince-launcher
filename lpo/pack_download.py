"""Shared pack download policy for the launcher and the local server."""
from urllib.parse import urlsplit
import urllib.request

DOWNLOAD_METHODS = ("auto", "pixeldrain", "custom")
PACK_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) littleprince-launcher/1.0"


def validate_pack_url(url):
    """Allow HTTP(S) mirrors/self-hosting, but never Google Drive."""
    url = str(url or "").strip()
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError("Pack URL must be an HTTP or HTTPS download link.")
    blocked = ("drive.google.com", "docs.google.com", "drive.usercontent.google.com",
               "googleusercontent.com")
    if any(host == domain or host.endswith("." + domain) for domain in blocked):
        raise ValueError("Google Drive downloads are disabled. Use Catbox, Pixeldrain or a self-hosted URL.")
    return url


def clean_download_settings(data):
    """An obsolete source choice becomes Auto; blocked custom links are ignored."""
    out = {"method": "auto", "custom": {}}
    if not isinstance(data, dict):
        return out
    method = str(data.get("method") or "").lower()
    if method in DOWNLOAD_METHODS:
        out["method"] = method
    custom = data.get("custom")
    if isinstance(custom, dict):
        for code, url in custom.items():
            try:
                out["custom"][str(code).strip()] = validate_pack_url(url)
            except ValueError:
                pass
    return out


class _PackRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_pack_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_pack(url, timeout=120):
    """Reject blocked links before connecting, including redirect destinations."""
    request = urllib.request.Request(validate_pack_url(url), headers={"User-Agent": PACK_UA})
    return urllib.request.build_opener(_PackRedirectHandler()).open(request, timeout=timeout)
