import codecs
import json

import pytest

from store.history import HistoryStore, HistoryStoreError, render_documents, render_index, rendered_ids, tokenize


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


def _ids(result) -> list[str]:
    return [doc.id for doc in result.documents]


def test_pregunta_por_persona_no_devuelve_todo_el_corpus(store):
    assert _ids(store.search("¿Quién es Valter Dabbene?")) == ["debates_origen_02"]


def test_nombre_inexistente_se_reporta_como_termino_sin_coincidencia(store):
    result = store.search("¿Quién es Lorenzo Dabbene?")
    assert _ids(result) == ["debates_origen_02"]
    assert result.unmatched_terms == ["lorenzo"]


def test_solo_stopwords_no_matchea_nada(store):
    result = store.search("¿Quién es?")
    assert (result.documents, result.unmatched_terms) == ([], [])
    assert tokenize("¿Quién es el de la?") == []


def test_ignora_acentos_y_mayusculas(store):
    assert store.search("FUNDACIÓN") == store.search("fundacion")
    assert len(store.search("fundacion").documents) == 3


def test_tolera_typo_de_una_letra(store):
    # llama3.2 manda 'fundacin' al perder la 'ó' en los argumentos de la tool.
    assert len(store.search("fundacin").documents) == 3


def test_numeros_no_usan_tolerancia_a_typos(store):
    assert store.search("1905").documents == []


@pytest.mark.parametrize("tema", ["historia de Las Varillas", "¿Qué sabés de Las Varillas?", "origen de Las Varillas"])
def test_pregunta_general_devuelve_corpus_sin_terminos_faltantes(store, tema):
    # Regresión: 'historia' no está en el corpus y devolvía 0 documentos + aviso «historia».
    result = store.search(tema)
    assert (len(result.documents), result.unmatched_terms) == (3, [])


def test_termino_presente_en_todos_solo_puntua_sin_terminos_especificos(store):
    result = store.search("intendente de Las Varillas")
    assert (len(result.documents), result.unmatched_terms) == (3, ["intendente"])


def test_sin_ninguna_coincidencia_no_hay_resultados(store):
    result = store.search("intendente xyzzy")
    assert (result.documents, result.unmatched_terms) == ([], ["intendente", "xyzzy"])


def test_coincidencia_parcial_devuelve_documento_y_aviso(store):
    result = store.search("¿Quién fue el primer intendente de Las Varillas?")
    assert _ids(result) == ["debates_origen_01"]  # 'primer núcleo poblacional'
    assert result.unmatched_terms == ["intendente"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("¿Quién fue Juan Alvarez?", ["Juan Alvarez"]),
        ("¿Quién es Lorenzo Dabbene?", ["Lorenzo Dabbene"]),
        ("¿Quién es Valter Dabbene?", []),
        ("Contame sobre el Centro de Estudios Parada KM 81", []),
        ("¿Qué pasó en Las Varillas?", []),
        ("Hola, ¿qué podés hacer?", []),
        ("Hola Valter Dabbene", []),
        ("Hola Juan Alvarez", ["Juan Alvarez"]),
        ("¿Dónde queda Las Varillas Córdoba?", []),
        ("¿Quién es Valter Rodríguez?", []),  # apellido desconocido: lo cubre el aviso por término
        ("Ana María Luisa Alvarez", []),  # más de 3 palabras: no se trata como nombre
    ],
)
def test_nombres_con_apellido_conocido_y_nombre_inexistente(store, question, expected):
    assert store.unknown_names(question) == expected


def test_ranking_prioriza_mas_coincidencias(store):
    assert _ids(store.search("ferrocarril 1900"))[0] == "debates_origen_01"


def test_tokens_enteros_no_substrings(store):
    assert store.search("ferro").documents == []


def test_id_exacto(store):
    assert _ids(store.search("debates_origen_03")) == ["debates_origen_03"]


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


def test_rendered_ids_extrae_cabeceras_sin_repetir(store):
    docs = list(store.documents)
    text = render_documents([docs[1], docs[0], docs[1]])
    assert rendered_ids(text) == [docs[1].id, docs[0].id]
    assert rendered_ids(render_index(docs)) == []
