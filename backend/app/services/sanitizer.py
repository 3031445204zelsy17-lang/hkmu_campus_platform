import html
import re


def sanitize(text: str | None) -> str | None:
    """HTML-escape user text before storing in database."""
    if text is None:
        return None
    return html.escape(text, quote=True)


def sanitize_dict(data: dict, *fields: str) -> dict:
    """Return a copy of data with specified fields HTML-escaped."""
    out = dict(data)
    for f in fields:
        if f in out and out[f] is not None:
            out[f] = sanitize(out[f])
    return out
