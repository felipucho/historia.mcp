"""Catálogo de proveedores de LLM: la única lista de ids válidos.

Agregar un proveedor: un miembro en ProviderId, su cliente y su registro en el lifespan de main.py.
ChatIn, /api/modelos y HistorianAgent salen de acá: ninguno repite la lista.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class ProviderId(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass(frozen=True)
class ProveedorInfo:
    """Lo que muestra el selector del chat: nombre para mostrar y si el proveedor tiene cliente registrado."""

    id: ProviderId
    nombre: str
    disponible: bool


def catalogo_proveedores(nombres: Mapping[ProviderId, str], *, registrados: Iterable[ProviderId]) -> list[ProveedorInfo]:
    """Un ítem por ProviderId, en orden del enum. Si falta un nombre, KeyError al arrancar (fail-fast)."""
    activos = frozenset(registrados)
    return [ProveedorInfo(id=provider, nombre=nombres[provider], disponible=provider in activos) for provider in ProviderId]
