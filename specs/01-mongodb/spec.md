# Spec 01 -- Persistencia en MongoDB

## Objetivo

Los libros y sus fragmentos viven en MongoDB. El backend y el servidor MCP leen de ahí, en lugar de `fundacion.json`. El MCP detecta libros publicados sin reiniciar. Fuera de `backend/` y `frontend/`, el único módulo que lee `fundacion.json` es la siembra (y los tests).

## Historias de usuario

- Como docente, quiero que la siembra cargue `fundacion.json` una sola vez, para que el chat responda igual que antes y no duplique datos al reejecutarla.
- Como lector del chat, quiero que un libro publicado sea consultable por el agente sin reiniciar el servidor.
- Como desarrollador, quiero correr las pruebas del repositorio sin levantar Mongo.

## Criterios de aceptación

- **A1.** Dado Mongo vacío, cuando ejecuto la siembra, entonces hay 1 libro y 3 fragmentos; si la ejecuto otra vez, siguen siendo 1 y 3. *(Ajustado de 6 a 3: el corpus actual tiene 3 documentos. Decisión del 2026-10-26.)*
- **A2.** Dado un fragmento con tags `["Ferrocarril", " ferrocarril ", "Estación"]`, cuando se guarda, entonces quedan `["ferrocarril", "estacion"]`.
- **A3.** Dado un libro en borrador, cuando el repositorio lista los libros publicados, entonces no aparece; al publicarlo aparece y `meta.version` aumenta en 1. *(El endpoint `/api/libros` llega en la parte C.)*
- **A4.** Dado el MCP en ejecución, cuando se publica un libro, entonces la siguiente llamada a una herramienta encuentra su contenido sin reiniciar procesos.
- **A5.** Dado `MONGODB_URL` inválida o Mongo apagado, cuando arranca el backend, entonces falla con un mensaje que nombra la variable a revisar y no imprime la contraseña.
- **A6.** Las pruebas del repositorio corren sin Mongo (con `FakeRepo`), y la misma batería pasa con `MongoBookRepository` cuando hay Mongo disponible.
- **A7.** *(Propuesto; no está en el plan.)* Dadas dos publicaciones casi simultáneas, cuando ambas terminan, entonces `meta.version` aumentó en 2 y ningún valor se repite.
- **A8.** Dado Mongo sin libros publicados, cuando arranca el backend, entonces arranca y el log avisa que no hay libros publicados. *(Sección 9, criterio 3 del plan.)*

## Fuera de alcance

- Backoffice, carga por partes, endpoints `/api/libros` y `/api/admin/*` (partes B y C).
- Nuevas herramientas MCP o cambios de prompt (parte D). La herramienta actual sigue igual; cambia solo de dónde lee.
- Archivos legacy en la raíz (`server.py`, `web.py`, `client.py`): siguen leyendo `fundacion.json`. Decisión del 2026-10-26.
- Migración de datos existentes: no hay. La siembra es la migración.
- Autenticación de Mongo más allá de la URI en `.env`.

## Preguntas abiertas

- [x] Driver: PyMongo sync o async. **Respuesta:** PyMongo sync (2026-10-26). El backend llama al repositorio con `asyncio.to_thread`.
- [x] Mongo local o Atlas. **Respuesta:** local 7.0 (2026-10-26).
- [x] A1: 6 fragmentos o 3. **Respuesta:** 3 (2026-10-26).
- [x] Legacy en la raíz y criterio 1. **Respuesta:** legacy excluido del criterio (2026-10-26).
- [ ] Slug duplicado. **Supuesto:** la siembra es idempotente por slug; un slug existente con otro contenido se rechaza con error. No se sobrescribe.
- [ ] Borrar un libro publicado. **Supuesto:** no hay borrado en esta spec. Llega en la parte C, con confirmación.
- [ ] Falta `fundacion.json` al sembrar. **Supuesto:** la siembra falla con un mensaje claro. El arranque del backend no depende de la siembra.

## Contrato que usa o expone

- Colecciones `libros`, `fragmentos` y `meta` (plan 4.2 y 17.1). Tags normalizados al guardar.
- Variables de entorno `MONGODB_URL` y `MONGODB_DB` (plan 17.4).
- Sin endpoints nuevos en esta spec.
- Interno: protocolo `BookRepository` (ver `plan.md`).
