# Plan 01 -- Persistencia en MongoDB

## Enfoque

El repositorio es la única puerta a Mongo. Backend y MCP dependen del protocolo `BookRepository`, no del driver. `MongoBookRepository` lo implementa con PyMongo sync. `FakeRepo` lo implementa en memoria para las pruebas.

Al arrancar, el backend carga los fragmentos publicados y arma el índice con el buscador por tokens que ya existe en `HistoryStore`, ampliado con `libro_slug`. El MCP hace lo mismo y vuelve a cargar cuando `meta.version` cambia. Es la opción 1 de la sección 4.3 del plan.

## Protocolo BookRepository

Métodos de esta parte. Los de administración que necesitan las partes B y C se agregan en esas partes.

| Método | Lo usa | Qué hace |
|---|---|---|
| `ping()` | Arranque (A5) | Verifica conexión con timeout corto. Lanza `RepositorioError` con la variable a revisar. |
| `version() -> int` | MCP | Lee `meta.version` (`_id: "corpus"`). Sin documento, devuelve 0. |
| `listar_publicados() -> list[Libro]` | API pública, MCP | Libros con `estado: "publicado"`. |
| `fragmentos_publicados() -> list[Fragmento]` | Backend, MCP | Fragmentos de libros publicados, para armar el índice. |
| `guardar_libro(libro)` | Siembra | Inserta. Mismo slug y mismo contenido: no hace nada (el estado no cuenta). Mismo slug y otro contenido: `SlugOcupado`. |
| `guardar_fragmentos(libro_slug, fragmentos)` | Siembra | Reemplaza los fragmentos del libro. Si el libro está publicado, sube `meta.version`. Tags normalizados (T3). |
| `publicar(slug) -> int` | Admin (parte C) | Cambia el estado y hace `$inc` a `meta.version`. Si ya estaba publicado, no cambia nada. Devuelve la versión vigente. |

## Cómo se entera el MCP de un libro nuevo

- **Qué consulta:** `version()`, un `find_one` por `_id` en `meta`. Una lectura por llamada a herramienta.
- **Costo:** un viaje de ida y vuelta a Mongo local por llamada. Se mide en la prueba a mano, no se estima acá.
- **Si cambió:** vuelve a leer los fragmentos publicados y arma un índice nuevo. Luego cambia la referencia de una vez. Las llamadas en curso siguen con el índice anterior.
- **Dos publicaciones casi simultáneas:** `publicar` usa `$inc` atómico, así que cada una recibe un número distinto. El MCP recarga desde Mongo completo, no aplica deltas. Si ve un valor intermedio, recarga en la llamada siguiente.
- **Caso de borde:** `meta` inexistente equivale a versión 0 y corpus vacío.

## Piezas

| Pieza | Responsabilidad | Criterios |
|---|---|---|
| `backend/store/repository.py` | Protocolo `BookRepository` y `RepositorioError` | A6 |
| `backend/store/mongo_repository.py` | `MongoBookRepository` con PyMongo sync, índices, `ping` | A1, A3, A5, A7 |
| `backend/store/tags.py` | `normalizar_tags(lista) -> lista` (minúsculas, sin acentos, sin duplicados) | A2 |
| `backend/tests/fake_repository.py` | `FakeRepo` en memoria, con versión manipulable | A4, A6 |
| `backend/store/history.py` | `HistoryStore` puede armarse desde documentos ya cargados. El buscador no cambia. `from_file` se mantiene para la siembra y los tests | A4 |
| `backend/scripts/seed_from_json.py` | Siembra idempotente desde `fundacion.json` | A1 |
| `backend/config.py` | `MONGODB_URL` (opcional) y `MONGODB_DB`; `main.py` exige la URL al arrancar | A5 |
| `backend/main.py` | Construye el repositorio en `lifespan`. Sin lógica de negocio | A5, A8 |
| `backend/mcp_server.py` | Lee del repositorio y compara `version()` en cada llamada | A4 |
| `backend/evals/eval_agent.py` | Pasa a leer del repositorio (requiere la base sembrada) | A4 |
| `backend/requirements.txt` | `pymongo` fijado a una versión verificada en PyPI | A1 |
| `.env.example` | Variables Mongo, sin credenciales reales | A5 |
| `README.md` | No existe hoy. Se crea con la sección de arranque | A5 |

## Decisiones y alternativas descartadas

- **PyMongo sync, no async.** El plan pide una sola librería en todo el curso, y el MCP corre sin servidor web. Se descartó async en todo el stack: no aporta nada al MCP y complica las pruebas.
- **Índice en memoria, no `$text`.** Conserva la tolerancia a acentos y errores de tipeo del buscador actual. El corpus es chico.
- **Recarga completa, no deltas.** Es simple y correcta. Con decenas de libros el costo es bajo.
- **`$inc` atómico, no leer y escribir.** Evita perder publicaciones simultáneas.
- **Índices por `libro_slug`, no por `libro_id`.** El contrato 17.1 no tiene `libro_id`. Índices: `libros.slug` único, `fragmentos.id` único, `fragmentos (libro_slug, orden)` y `fragmentos.tags`.
- **Orden de escritura: contenido primero, versión después.** Vale para `publicar` y para `guardar_fragmentos` de un libro publicado.
- **Tags normalizados en el modelo `Fragmento`, no en cada repositorio.** Lo hace `normalizar_tags` (`store/tags.py`) con un validador. Fake, Mongo y la siembra quedan con las mismas reglas.
- **Reenviar fragmentos idénticos no sube la versión.** La re-siembra deja `meta.version` igual.
- **La siembra exige `--autor` y `--anio`.** El plan no define esos datos, así que no se inventan. `MONGODB_URL` y `MONGODB_DB` son opcionales en `config.py` hasta T5; la siembra falla si falta la URL.
- **El arranque del backend lee de Mongo (T5).** `lifespan` abre el repositorio, lee los fragmentos publicados y cierra la conexión. Sin URL, o con una URL que no conecta, el arranque falla. El error nombra `MONGODB_URL` y no muestra la URL.
- **Mongo vacío arranca.** `HistoryStore(..., permitir_vacio=True)` y un warning `sin_libros_publicados`. `/api/fundacion` devuelve `raw: []`.
- **El backend no se refresca sin reiniciar.** El prompt y `/api/fundacion` quedan con lo leído al arrancar.
- **El MCP sí se refresca (T6).** En cada llamada lee `meta.version` y recarga solo si cambió (`CorpusVivo`, `store/corpus.py`). La versión se lee antes de cargar, así que un cambio durante la carga provoca otra recarga en la llamada siguiente.
- **El subproceso MCP recibe `MONGODB_URL` y `MONGODB_DB` por entorno**, no `DATA_FILE`. Las evals necesitan la base sembrada.

## Riesgos

- **Mongo caído a mitad de uso.** La llamada del MCP falla y el backend responde `tools_unavailable`, como hoy. Mitigación: timeout corto en `ping` y errores capturados.
- **Tests que necesitan Mongo.** Van marcados aparte (`pytest -m mongo`) y se saltan si no hay `MONGODB_URL` de prueba.
- **Corte entre escribir fragmentos y subir la versión.** El MCP queda con contenido viejo hasta el próximo cambio de versión. Sin transacciones (instancia única). Mitigación: reenviar la carga, que es idempotente.
- **`mongod` fuera de PATH.** Mongo 7.0 está instalado en `C:\Program Files\MongoDB\Server\7.0`. La app solo necesita la URI. Para levantar el servidor hace falta la ruta completa o el servicio de Windows.

## Pruebas

- **Con dobles (`FakeRepo`), sin red:** A2 (`normalizar_tags`), A6 (batería del repositorio), lógica de recarga del MCP (A4) publicando entre dos llamadas, y A8 (corpus vacío).
- **Con Mongo real, marcadas aparte:** A1 (sembrar dos veces), A3, A5 (URI mala y Mongo apagado), A7 (dos `publicar` en paralelo).
- **Mongo real:** `MONGODB_URL_TEST=mongodb://127.0.0.1:27017/ pytest -m mongo`. Usa la base `historia_test` y la borra antes y después. Nunca toca la base de la aplicación.
- **A mano:** Compass (colecciones, índices, `meta.version`), sembrar dos veces, apagar Mongo y arrancar el backend.
