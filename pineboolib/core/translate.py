"""Translate module."""


def translate(group: str, context: str) -> str:
    """Return the translation if it exists."""
    from PyQt5 import Qt

    return Qt.qApp.translate(group.encode(), context.encode())
