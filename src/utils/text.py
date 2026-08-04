# src/utils/text.py


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
