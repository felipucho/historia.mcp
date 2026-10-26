# Verificación: spec 01 (persistencia en MongoDB)

Fecha: 2026-10-26. Estados según el plan (18.2): Cumple, Equivalente, Parcial, Falta, Sin verificar. Las rutas apuntan a la línea de la definición.

Comandos de prueba:
- Sin Mongo: `pytest` desde `backend/` → 183 pasan, 26 se saltan.
- Con Mongo: `MONGODB_URL_TEST=mongodb://127.0.0.1:27017/ pytest` → 209 pasan.
- `ruff check backend` → sin errores.

## Criterios A1 a A8

| Criterio | Estado | Evidencia |
|---|---|---|
| A1. Siembra dos veces: 1 libro y 3 fragmentos | Cumple (ajustado a 3 fragmentos) | `backend/tests/test_seed.py:10` (corre con `repo[fake]` y `repo[mongo]`). Corrida real de `python -m scripts.seed_from_json` dos veces contra una base de prueba: 1 libro publicado, 3 fragmentos, `meta.version = 1` en ambas. Idempotencia en `backend/store/mongo_repository.py:78` (guardar_fragmentos ignora contenido idéntico). |
| A2. Tags normalizados al guardar | Cumple | `backend/store/tags.py:8` (`normalizar_tags`), validador en `backend/store/repository.py:43` (Fragmento). Pruebas: `backend/tests/test_tags.py:5`, `backend/tests/test_repository.py:104`. |
| A3. Borrador fuera del listado, publicar sube la versión en 1 | Cumple | `backend/store/mongo_repository.py:103` (publicar). Prueba: `backend/tests/test_repository.py:39`. El endpoint `/api/libros` llega en la parte C; el criterio cubre el repositorio. |
| A4. El MCP encuentra un libro publicado sin reiniciar | Cumple | `backend/store/corpus.py:24` (CorpusVivo), `:37` (store). Pruebas: `backend/tests/test_mcp_registry.py:159` (en memoria, `repo[fake]` y `repo[mongo]`), `backend/tests/test_corpus.py:23`. Entre procesos: un script publicó desde otro proceso y el subproceso `python -m mcp_server` ya corriendo devolvió el contenido nuevo, con `meta.version = 1`. El script está en el scratchpad de la sesión y no se versiona. |
| A5. URL inválida o Mongo apagado: falla, nombra la variable, no imprime la contraseña | Cumple | `backend/main.py:42` (`url_mongodb`), `:49` (`abrir_repositorio`), `backend/store/mongo_repository.py:35` (`from_url`, errores sin URL). Pruebas: `backend/tests/test_arranque.py:7` y `:14`, `backend/tests/test_mongo_repository.py:8` y `:17`, `backend/tests/test_seed.py:40` y `:47`. Manual: backend con URL `http://usuario:secreta@…` → sale con código 3 y el error `MONGODB_URL no funciona: La URL de conexión tiene un formato inválido…`; con puerto 1 → `No se pudo conectar a MongoDB`; sin URL → `Falta MONGODB_URL en .env`. `secreta` aparece 0 veces en los logs. |
| A6. Pruebas sin Mongo con FakeRepo; misma batería con Mongo real | Cumple | Fixture `repo` en `backend/tests/conftest.py`: corre cada prueba de `test_repository.py` con `fake` y con `mongo`. Sin Mongo: 183 pasan, 26 se saltan. Con Mongo: 209 pasan. |
| A7. Dos publicaciones simultáneas: versiones distintas, sin repetir | Cumple (criterio propuesto, no está en el plan) | `backend/tests/test_repository.py:60` (`repo[fake]` y `repo[mongo]`): dos publicaciones en hilos dan versiones `{1, 2}` y `version() == 2`. Implementación: `$inc` atómico en `backend/store/mongo_repository.py:120` (`_subir_version`). |
| A8. Mongo sin libros: arranca y avisa | Cumple | `backend/tests/test_arranque.py:25` (`HistoryStore` vacío solo con `permitir_vacio=True`). Manual: backend contra base vacía → `GET /api/fundacion` devuelve `{"raw":[],"full_text":""}` y el log tiene `sin_libros_publicados` (`backend/main.py:77`). |

## Criterio 1 de la sección 9 del plan (ningún módulo lee fundacion.json salvo la siembra y los tests)

Cumple, con la excepción de los archivos legacy de la raíz, decidida el 2026-10-26.

Verificado con `grep` sobre `backend/` sin `tests/`:
- `backend/store/history.py:122` define `from_file`. Lo usan la siembra y los tests.
- `backend/config.py:23` es el default de `--datos` del script de siembra.
- Las demás menciones son comentarios.

## Checklist de la tarea (plan 18.1)

- [x] Las pruebas pasan y se ejecutaron en ambos modos.
- [x] Comportamiento real probado: arranque con base vacía, siembra dos veces, MCP entre procesos y arranques con URL inválida.
- [ ] Diff completo leído por el dueño del proyecto. Pendiente.
- [x] La spec refleja lo que hace. `CLAUDE.md` no se modifica por pedido del dueño (2026-10-26): las decisiones quedan en la spec. T0 queda cancelada en `tasks.md`.
- [x] Sin secretos: `.env` está en `.gitignore` (`.gitignore:5`). Las URLs con credenciales aparecen solo en pruebas, con valores de prueba. `.env.example` no tiene credenciales.

## Sin verificar

- **Compass** (colecciones, índices, `meta.version`): no se abrió. Los índices los crea `_asegurar_indices` (`backend/store/mongo_repository.py:137`) y no se comprobaron a mano.
- **Detener el servicio real de Mongo**: no se hizo. El caso de Mongo apagado se simuló con el puerto 1.
- **Evals contra Ollama** (`backend/evals/eval_agent.py`): no se corrieron. Necesitan Ollama y la base sembrada con el libro real.
- **Siembra en la base `historia`**: no se hizo. Falta autor y año del libro semilla.

## Desviaciones de la spec

- A1: 3 fragmentos en lugar de 6 (el corpus tiene 3 documentos). Decisión del 2026-10-26.
- A7: no estaba en el plan. Se agregó como criterio propuesto.
- `listar_publicados` devuelve `list[Libro]` en lugar de `LibroResumen`.
- Índices por `libro_slug` en lugar de `libro_id`, porque el contrato 17.1 no tiene `libro_id`.
- Reenviar fragmentos idénticos no sube `meta.version`. Lo agregó T4 para que la re-siembra sea idempotente.
- `MONGODB_URL` es opcional en `Settings`. `main.py` exige la URL al arrancar y el script de siembra la exige antes de conectar.

## Fuera de alcance de esta spec

Backoffice, carga por partes, endpoints `/api/libros` y `/api/admin/*`, y los criterios de las partes B, C y D.
