"""Normalización de tags (plan 4.2): minúsculas, sin acentos, sin espacios sobrantes ni repetidos."""

from collections.abc import Iterable

from store.history import normalize


def normalizar_tags(tags: Iterable[str]) -> list[str]:
    """Devuelve los tags normalizados en orden de primera aparición, sin vacíos ni repetidos."""
    normalizados = (" ".join(normalize(tag).split()) for tag in tags)
    return list(dict.fromkeys(tag for tag in normalizados if tag))
