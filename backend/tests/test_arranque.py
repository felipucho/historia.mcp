import main
import pytest
from pydantic import SecretStr
from store.history import HistoryStore, HistoryStoreError


def test_criterio_a5_sin_mongodb_url_el_arranque_falla_y_nombra_la_variable(monkeypatch):
    monkeypatch.setattr(main.settings, "mongodb_url", None)

    with pytest.raises(RuntimeError, match="MONGODB_URL"):
        main.abrir_repositorio()


def test_criterio_a5_url_invalida_no_filtra_la_contrasena(monkeypatch):
    monkeypatch.setattr(main.settings, "mongodb_url", SecretStr("http://usuario:secreta@127.0.0.1:27017/"))

    with pytest.raises(RuntimeError) as exc:
        main.abrir_repositorio()

    assert "MONGODB_URL" in str(exc.value)
    assert "secreta" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_criterio_a8_historia_store_vacio_solo_se_permite_explicitamente():
    store = HistoryStore([], permitir_vacio=True)

    assert store.documents == ()
    assert store.search("historia").documents == []
    with pytest.raises(HistoryStoreError):
        HistoryStore([])
