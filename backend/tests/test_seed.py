from pydantic import SecretStr
from scripts import seed_from_json
from scripts.seed_from_json import construir_libro, fragmentos_desde, main, sembrar


def _libro():
    return construir_libro("debates-origen", "Debates sobre el origen", "Autor de prueba", 2024, "secundaria")


def test_criterio_a1_sembrar_dos_veces_deja_un_libro_y_tres_fragmentos(repo, store):
    sembrar(repo, store, _libro())
    sembrar(repo, store, _libro())

    assert [libro.slug for libro in repo.listar_publicados()] == ["debates-origen"]
    assert len(repo.fragmentos_publicados()) == 3


def test_la_siembra_publica_el_libro_y_conserva_la_metadata(repo, store):
    version = sembrar(repo, store, _libro())

    assert version == 1
    fragmento = {f.id: f for f in repo.fragmentos_publicados()}[store.documents[0].id]
    assert fragmento.metadata == store.documents[0].metadata.model_dump()


def test_fragmentos_desde_numera_en_el_orden_del_archivo(store):
    fragmentos = fragmentos_desde(store, "debates-origen")

    assert [f.id for f in fragmentos] == [doc.id for doc in store.documents]
    assert [f.orden for f in fragmentos] == [1, 2, 3]


def test_main_sin_archivo_de_datos_falla_con_mensaje(tmp_path, capsys):
    codigo = main(["--autor", "Autor", "--anio", "2024", "--datos", str(tmp_path / "nada.json")])

    assert codigo == 1
    assert "No existe el archivo de datos" in capsys.readouterr().err


def test_main_sin_mongodb_url_falla_y_nombra_la_variable(monkeypatch, capsys):
    monkeypatch.setattr(seed_from_json.settings, "mongodb_url", None)

    assert main(["--autor", "Autor", "--anio", "2024"]) == 1
    assert "MONGODB_URL" in capsys.readouterr().err


def test_main_con_url_invalida_no_imprime_la_contrasena(monkeypatch, capsys):
    monkeypatch.setattr(seed_from_json.settings, "mongodb_url", SecretStr("http://usuario:secreta@127.0.0.1:27017/"))

    assert main(["--autor", "Autor", "--anio", "2024"]) == 1
    assert "secreta" not in capsys.readouterr().err
