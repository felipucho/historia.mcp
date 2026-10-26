import pytest
from pymongo.errors import DuplicateKeyError
from store.mongo_repository import MongoBookRepository
from store.repository import RepositorioError


# Sin servidor ni red: la URL falla al parsearse.
def test_criterio_a5_url_con_formato_invalido_no_filtra_la_contrasena():
    with pytest.raises(RepositorioError) as exc:
        MongoBookRepository.from_url("http://usuario:secreta@127.0.0.1:27017/", "historia_test")

    assert "secreta" not in str(exc.value)
    assert exc.value.__cause__ is None


# Puerto 1 en loopback: nada escucha ahí, y el timeout es corto.
def test_criterio_a5_servidor_apagado_no_filtra_la_contrasena():
    with pytest.raises(RepositorioError) as exc:
        MongoBookRepository.from_url("mongodb://usuario:secreta@127.0.0.1:1/", "historia_test", timeout_ms=300)

    assert "secreta" not in str(exc.value)
    assert exc.value.__cause__ is None


@pytest.mark.mongo
def test_indice_unico_rechaza_id_de_fragmento_repetido(mongo_repo):
    documento = {
        "id": "x_01",
        "libro_slug": "x",
        "orden": 1,
        "titulo": "Título",
        "contenido": "Texto",
        "tags": [],
        "metadata": {},
        "tagueo": {"origen": "manual", "revisado": True},
    }
    mongo_repo._fragmentos.insert_one(dict(documento))

    with pytest.raises(DuplicateKeyError):
        mongo_repo._fragmentos.insert_one(dict(documento))
