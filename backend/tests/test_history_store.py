import codecs
import json

import pytest

from store.history import HistoryStore, HistoryStoreError, tokenize


def _write(tmp_path, content: bytes | str):
    path = tmp_path / "fundacion.json"
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def _doc(doc_id: str = "doc_1", **overrides) -> dict:
    doc = {
        "id": doc_id,
        "titulo": "Título",
        "contenido": "Contenido",
        "tags": [],
        "metadata": {"criterio_historiografico": "c", "fecha_clave": "f", "fuente": "s"},
    }
    return doc | overrides


def test_carga_corpus_real(store):
    assert [doc.id for doc in store.documents] == ["debates_origen_01", "debates_origen_02", "debates_origen_03"]


def test_full_text_formato_titulo_contenido(store):
    first, second = store.documents[:2]
    assert store.full_text.startswith(f"## {first.titulo}\n{first.contenido}\n\n## {second.titulo}\n")


def test_pregunta_por_persona_no_devuelve_todo_el_corpus(store):
    assert [doc.id for doc in store.search("¿Quién es Lorenzo Dabbene?")] == ["debates_origen_02"]


def test_solo_stopwords_no_matchea_nada(store):
    assert store.search("¿Quién es?") == []
    assert tokenize("¿Quién es el de la?") == []


def test_ignora_acentos_y_mayusculas(store):
    assert store.search("FUNDACIÓN") == store.search("fundacion")
    assert len(store.search("fundacion")) == 3


def test_ranking_prioriza_mas_coincidencias(store):
    assert store.search("ferrocarril 1900")[0].id == "debates_origen_01"


def test_tokens_enteros_no_substrings(store):
    assert store.search("ferro") == []


def test_id_exacto(store):
    assert [doc.id for doc in store.search("debates_origen_03")] == ["debates_origen_03"]


def test_archivo_inexistente(tmp_path):
    with pytest.raises(HistoryStoreError, match="No existe"):
        HistoryStore.from_file(tmp_path / "nada.json")


def test_json_corrupto(tmp_path):
    with pytest.raises(HistoryStoreError, match="inválido"):
        HistoryStore.from_file(_write(tmp_path, '[{"id": "x",'))


def test_schema_invalido(tmp_path):
    doc = _doc()
    del doc["titulo"]
    with pytest.raises(HistoryStoreError, match="inválido"):
        HistoryStore.from_file(_write(tmp_path, json.dumps([doc])))


def test_id_no_apto_para_ancla(tmp_path):
    with pytest.raises(HistoryStoreError):
        HistoryStore.from_file(_write(tmp_path, json.dumps([_doc('x" onmouseover="alert(1)')])))


def test_ids_duplicados(tmp_path):
    with pytest.raises(HistoryStoreError, match="duplicados"):
        HistoryStore.from_file(_write(tmp_path, json.dumps([_doc("a"), _doc("a")])))


def test_corpus_vacio(tmp_path):
    with pytest.raises(HistoryStoreError, match="vacío"):
        HistoryStore.from_file(_write(tmp_path, "[]"))


def test_acepta_bom_utf8(tmp_path):
    path = _write(tmp_path, codecs.BOM_UTF8 + json.dumps([_doc()]).encode("utf-8"))
    assert HistoryStore.from_file(path).documents[0].id == "doc_1"
