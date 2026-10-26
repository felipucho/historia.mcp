from scripts.seed_from_json import construir_libro, sembrar
from store.corpus import CorpusVivo, documentos_publicados


def _libro():
    return construir_libro("debates-origen", "Debates", "Autor de prueba", 2024, "secundaria")


def test_documentos_publicados_devuelve_el_corpus_sembrado(repo, store):
    sembrar(repo, store, _libro())

    documentos = documentos_publicados(repo)

    assert [(d.id, d.titulo, d.contenido, d.metadata) for d in documentos] == [
        (d.id, d.titulo, d.contenido, d.metadata) for d in store.documents
    ]


def test_sin_libros_publicados_devuelve_lista_vacia(repo):
    assert documentos_publicados(repo) == []


def test_criterio_a4_corpus_vivo_ve_el_libro_publicado_sin_reiniciar(repo, store):
    corpus = CorpusVivo(repo)
    assert corpus.store().documents == ()

    sembrar(repo, store, _libro())

    assert [d.id for d in corpus.store().documents] == [d.id for d in store.documents]


def test_corpus_vivo_no_recarga_si_la_version_no_cambia(repo, store):
    sembrar(repo, store, _libro())
    corpus = CorpusVivo(repo)
    primero = corpus.store()

    assert corpus.store() is primero
