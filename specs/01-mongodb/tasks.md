# Tareas 01 -- Persistencia en MongoDB

- [-] **T0** Cancelada por decisión del dueño: `CLAUDE.md` no se toca. Las decisiones quedan en esta spec (PyMongo sync, criterio 1 sin legacy, `fundacion.json` solo como semilla).
  - Cubre: constitución (plan 15)
  - Se comprueba con: lectura del diff de `CLAUDE.md`.

- [x] **T1** Protocolo `BookRepository`, `FakeRepo` y batería de pruebas del repositorio.
  - Cubre: A6, A4 (parcial)
  - Se comprueba con: `pytest tests/test_repository.py` pasa con `FakeRepo`.

- [x] **T2** `MongoBookRepository` que pasa la misma batería. Agregar `pymongo` fijado a `requirements.txt`.
  - Cubre: A1, A3, A6, A7
  - Se comprueba con: `pytest -m mongo` contra `MONGODB_URL` de prueba. Dos `publicar` en paralelo dan versiones distintas.

- [x] **T3** Normalización de tags al guardar.
  - Cubre: A2
  - Se comprueba con: `pytest tests/test_tags.py` con el caso exacto del criterio.

- [x] **T4** Siembra idempotente desde `fundacion.json`.
  - Cubre: A1
  - Se comprueba con: ejecutar dos veces y verificar en Compass 1 libro y 3 fragmentos.

- [x] **T5** Backend lee del repositorio. `MONGODB_URL` y `MONGODB_DB` validados. Falla con mensaje claro si no conecta.
  - Cubre: A5, A8
  - Se comprueba con: URI mala muestra la variable y no la contraseña. Mongo vacío arranca y avisa.

- [x] **T6** MCP lee del repositorio y compara `version()` en cada llamada. Recarga el índice cuando cambia.
  - Cubre: A4
  - Se comprueba con: test con `FakeRepo` que publica entre dos llamadas. A mano: publicar y consultar sin reiniciar el MCP.

- [x] **T7** `.env.example` y sección de arranque en `README.md` (el archivo no existe; se crea).
  - Cubre: A5
  - Se comprueba con: copiar `.env.example` a `.env` y arrancar sin tocar nada más.
