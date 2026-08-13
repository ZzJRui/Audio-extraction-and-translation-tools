def sanitize_utf8_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8")
