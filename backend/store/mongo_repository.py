"""Persistencia en MongoDB con PyMongo sync. Sin conocimiento de HTTP, MCP ni LLM."""

from collections.abc import Sequence
from datetime import UTC, datetime

from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import ConfigurationError, DuplicateKeyError, PyMongoError

from store.repository import (
    BookRepository,
    Fragmento,
    Libro,
    RepositorioError,
    SlugOcupado,
    contenido_de,
)

CORPUS_ID = "corpus"
# Dos publicaciones a la vez pueden chocar en el upsert de meta. El reintento resuelve el choque.
_INTENTOS_VERSION = 3


# SOLID-L (sustitución de Liskov): cumple BookRepository con la misma semántica que FakeRepo.
class MongoBookRepository(BookRepository):
    """Colecciones libros, fragmentos y meta (plan 4.2). Los errores de conexión salen como RepositorioError."""

    def __init__(self, client: MongoClient, db_name: str) -> None:
        db = client[db_name]
        self._client = client
        self._libros = db["libros"]
        self._fragmentos = db["fragmentos"]
        self._meta = db["meta"]

    @classmethod
    def from_url(cls, url: str, db_name: str, *, timeout_ms: int = 3000) -> "MongoBookRepository":
        """Conecta, verifica el servidor y asegura los índices.

        Ningún error incluye la URL, que puede llevar la contraseña. Quien llama nombra la variable que la contiene.
        """
        try:
            client = MongoClient(url, serverSelectionTimeoutMS=timeout_ms, tz_aware=True)
        except ConfigurationError:
            raise RepositorioError("La URL de conexión tiene un formato inválido") from None
        repo = cls(client, db_name)
        try:
            repo.ping()
            repo._asegurar_indices()
        except RepositorioError:
            client.close()
            raise
        return repo

    def ping(self) -> None:
        try:
            self._client.admin.command("ping")
        except PyMongoError:
            raise RepositorioError("No se pudo conectar a MongoDB") from None

    def cerrar(self) -> None:
        self._client.close()

    def version(self) -> int:
        doc = self._meta.find_one({"_id": CORPUS_ID}, {"version": 1})
        return doc["version"] if doc else 0

    def guardar_libro(self, libro: Libro) -> None:
        existente = self._libros.find_one({"slug": libro.slug}, {"_id": 0})
        if existente is None:
            try:
                self._libros.insert_one(libro.model_dump() | {"creado": datetime.now(UTC)})
                return
            except DuplicateKeyError:
                # Otro proceso lo insertó entre la lectura y el insert: se compara como cualquier existente.
                existente = self._libros.find_one({"slug": libro.slug}, {"_id": 0})
        if contenido_de(Libro.model_validate(existente)) != contenido_de(libro):
            raise SlugOcupado(f"El slug {libro.slug!r} ya existe con otro contenido")

    def guardar_fragmentos(self, libro_slug: str, fragmentos: Sequence[Fragmento]) -> None:
        libro = self._libros.find_one({"slug": libro_slug}, {"estado": 1})
        if libro is None:
            raise RepositorioError(f"No existe el libro {libro_slug!r}")
        if any(fragmento.libro_slug != libro_slug for fragmento in fragmentos):
            raise RepositorioError("Hay fragmentos que pertenecen a otro libro")
        ids = [fragmento.id for fragmento in fragmentos]
        if len(set(ids)) != len(ids):
            raise RepositorioError("Hay IDs de fragmento repetidos dentro del libro")
        ajenos = self._fragmentos.distinct("id", {"id": {"$in": ids}, "libro_slug": {"$ne": libro_slug}})
        if repetidos := sorted(ajenos):
            raise RepositorioError(f"IDs de fragmento ya usados por otro libro: {', '.join(repetidos)}")
        actuales = {doc["id"]: doc for doc in self._fragmentos.find({"libro_slug": libro_slug}, {"_id": 0})}
        if actuales == {fragmento.id: fragmento.model_dump() for fragmento in fragmentos}:
            return
        # Sin transacciones (instancia única): si la operación se corta acá, reenviar la misma carga la deja bien.
        self._fragmentos.delete_many({"libro_slug": libro_slug})
        if fragmentos:
            try:
                self._fragmentos.insert_many([fragmento.model_dump() for fragmento in fragmentos])
            except DuplicateKeyError as exc:
                raise RepositorioError("IDs de fragmento ya usados por otro libro") from exc
        if libro["estado"] == "publicado":
            self._subir_version()

    def publicar(self, slug: str) -> int:
        # Primero el estado y después la versión: quien lee la versión nunca ve un número nuevo sin el cambio.
        resultado = self._libros.update_one({"slug": slug, "estado": "borrador"}, {"$set": {"estado": "publicado"}})
        if resultado.modified_count:
            return self._subir_version()
        if self._libros.count_documents({"slug": slug}, limit=1) == 0:
            raise RepositorioError(f"No existe el libro {slug!r}")
        return self.version()

    def listar_publicados(self) -> list[Libro]:
        return [Libro.model_validate(doc) for doc in self._libros.find({"estado": "publicado"}, {"_id": 0})]

    def fragmentos_publicados(self) -> list[Fragmento]:
        slugs = self._libros.distinct("slug", {"estado": "publicado"})
        cursor = self._fragmentos.find({"libro_slug": {"$in": slugs}}, {"_id": 0})
        return [Fragmento.model_validate(doc) for doc in cursor.sort([("libro_slug", ASCENDING), ("orden", ASCENDING)])]

    def _subir_version(self) -> int:
        for _ in range(_INTENTOS_VERSION - 1):
            try:
                return self._incrementar_version()
            except DuplicateKeyError:
                continue
        return self._incrementar_version()

    def _incrementar_version(self) -> int:
        doc = self._meta.find_one_and_update(
            {"_id": CORPUS_ID},
            {"$inc": {"version": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["version"]

    def _asegurar_indices(self) -> None:
        try:
            self._libros.create_index([("slug", ASCENDING)], unique=True)
            self._fragmentos.create_index([("id", ASCENDING)], unique=True)
            self._fragmentos.create_index([("libro_slug", ASCENDING), ("orden", ASCENDING)])
            self._fragmentos.create_index([("tags", ASCENDING)])
        except PyMongoError:
            raise RepositorioError("No se pudieron crear los índices") from None
