"""Siembra fundacion.json como libro publicado en MongoDB. Idempotente: reejecutarla no duplica datos.

Uso (desde backend/, con .venv activo):
    python -m scripts.seed_from_json --autor "<autor>" --anio <año>
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from config import Settings
from pydantic import ValidationError
from store.history import HistoryStore, HistoryStoreError
from store.mongo_repository import MongoBookRepository
from store.repository import BookRepository, Fragmento, Libro, RepositorioError

settings = Settings()


def construir_libro(slug: str, titulo: str, autor: str, anio: int, fuente_tipo: str) -> Libro:
    return Libro(slug=slug, titulo=titulo, autor=autor, anio=anio, fuente_tipo=fuente_tipo)


def fragmentos_desde(store: HistoryStore, libro_slug: str) -> list[Fragmento]:
    """Un fragmento por documento, en el orden del archivo. El id se conserva: es el ancla del lector."""
    return [
        Fragmento(
            id=doc.id,
            libro_slug=libro_slug,
            orden=orden,
            titulo=doc.titulo,
            contenido=doc.contenido,
            tags=doc.tags,
            metadata=doc.metadata.model_dump(),
        )
        for orden, doc in enumerate(store.documents, start=1)
    ]


def sembrar(repo: BookRepository, store: HistoryStore, libro: Libro) -> int:
    """Guarda el libro y sus fragmentos, y lo publica para que el chat lo use. Devuelve meta.version."""
    repo.guardar_libro(libro)
    repo.guardar_fragmentos(libro.slug, fragmentos_desde(store, libro.slug))
    return repo.publicar(libro.slug)


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Siembra fundacion.json como libro publicado.")
    parser.add_argument("--slug", default="debates-origen")
    parser.add_argument("--titulo", default="Debates sobre el origen de Las Varillas")
    parser.add_argument("--autor", required=True)
    parser.add_argument("--anio", type=int, required=True)
    parser.add_argument("--fuente-tipo", choices=["primaria", "secundaria"], default="secundaria")
    parser.add_argument("--datos", type=Path, default=settings.data_file)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _argumentos(argv)
    try:
        store = HistoryStore.from_file(args.datos)
        libro = construir_libro(args.slug, args.titulo, args.autor, args.anio, args.fuente_tipo)
    except (HistoryStoreError, ValidationError) as exc:
        print(f"Siembra cancelada: {exc}", file=sys.stderr)
        return 1
    url = settings.mongodb_url.get_secret_value() if settings.mongodb_url else ""
    if not url:
        print("Siembra cancelada: falta MONGODB_URL en .env", file=sys.stderr)
        return 1
    try:
        repo = MongoBookRepository.from_url(url, settings.mongodb_db)
    except RepositorioError as exc:
        print(f"Siembra cancelada: {exc}. Revisá MONGODB_URL en .env", file=sys.stderr)
        return 1
    try:
        version = sembrar(repo, store, libro)
    except RepositorioError as exc:
        print(f"Siembra cancelada: {exc}", file=sys.stderr)
        return 1
    finally:
        repo.cerrar()
    print(f"Libro {libro.slug!r} publicado: {len(store.documents)} fragmentos, meta.version = {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
