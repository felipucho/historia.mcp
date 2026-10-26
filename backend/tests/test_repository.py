from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from store.repository import (
    Fragmento,
    Libro,
    RepositorioError,
    SlugOcupado,
)


def _libro(slug: str = "debates-origen", **cambios) -> Libro:
    base = {
        "slug": slug,
        "titulo": "Debates sobre el origen",
        "autor": "Autor de prueba",
        "anio": 2024,
        "fuente_tipo": "secundaria",
    }
    return Libro(**(base | cambios))


def _fragmento(libro_slug: str = "debates-origen", orden: int = 1, **cambios) -> Fragmento:
    base = {
        "id": f"{libro_slug.replace('-', '_')}_{orden:02d}",
        "libro_slug": libro_slug,
        "orden": orden,
        "titulo": f"Sección {orden}",
        "contenido": f"Texto del fragmento {orden}.",
    }
    return Fragmento(**(base | cambios))


def test_version_empieza_en_cero(repo):
    assert repo.version() == 0


def test_criterio_a3_borrador_no_aparece_hasta_publicar(repo):
    repo.guardar_libro(_libro())
    assert repo.listar_publicados() == []

    assert repo.publicar("debates-origen") == 1
    assert [libro.slug for libro in repo.listar_publicados()] == ["debates-origen"]


def test_publicar_dos_veces_no_sube_la_version(repo):
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")

    assert repo.publicar("debates-origen") == 1
    assert repo.version() == 1


def test_publicar_libro_inexistente_falla(repo):
    with pytest.raises(RepositorioError):
        repo.publicar("no-existe")


def test_criterio_a7_publicaciones_simultaneas_no_repiten_version(repo):
    repo.guardar_libro(_libro())
    repo.guardar_libro(_libro("otro-libro"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        versiones = list(pool.map(repo.publicar, ["debates-origen", "otro-libro"]))

    assert sorted(versiones) == [1, 2]
    assert repo.version() == 2


def test_guardar_libro_mismo_contenido_no_duplica(repo):
    repo.guardar_libro(_libro())
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")

    assert len(repo.listar_publicados()) == 1


def test_guardar_libro_no_compara_el_estado(repo):
    # La siembra vuelve a guardar el libro borrador después de que el libro ya fue publicado.
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")
    repo.guardar_libro(_libro())

    assert [libro.estado for libro in repo.listar_publicados()] == ["publicado"]


def test_guardar_libro_con_otro_contenido_rechaza(repo):
    repo.guardar_libro(_libro())

    with pytest.raises(SlugOcupado):
        repo.guardar_libro(_libro(titulo="Otro título"))


def test_guardar_fragmentos_reemplaza_en_vez_de_acumular(repo):
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")
    repo.guardar_fragmentos("debates-origen", [_fragmento(orden=1), _fragmento(orden=2)])
    repo.guardar_fragmentos("debates-origen", [_fragmento(orden=1)])

    assert [f.id for f in repo.fragmentos_publicados()] == ["debates_origen_01"]


def test_criterio_a2_tags_se_normalizan_al_guardar(repo):
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")
    repo.guardar_fragmentos("debates-origen", [_fragmento(tags=["Ferrocarril", " ferrocarril ", "Estación"])])

    assert repo.fragmentos_publicados()[0].tags == ["ferrocarril", "estacion"]


def test_fragmentos_de_borrador_no_aparecen(repo):
    repo.guardar_libro(_libro())
    repo.guardar_fragmentos("debates-origen", [_fragmento()])

    assert repo.fragmentos_publicados() == []


def test_guardar_fragmentos_de_libro_inexistente_falla(repo):
    with pytest.raises(RepositorioError):
        repo.guardar_fragmentos("no-existe", [_fragmento(libro_slug="no-existe")])


def test_guardar_fragmentos_de_otro_libro_falla(repo):
    repo.guardar_libro(_libro())
    repo.guardar_libro(_libro("otro-libro"))

    with pytest.raises(RepositorioError):
        repo.guardar_fragmentos("debates-origen", [_fragmento(libro_slug="otro-libro")])


def test_ids_repetidos_dentro_del_libro_fallan(repo):
    repo.guardar_libro(_libro())

    with pytest.raises(RepositorioError):
        repo.guardar_fragmentos("debates-origen", [_fragmento(orden=1), _fragmento(orden=1)])


def test_ids_repetidos_entre_libros_fallan(repo):
    repo.guardar_libro(_libro())
    repo.guardar_libro(_libro("otro-libro"))
    repo.guardar_fragmentos("debates-origen", [_fragmento(orden=1)])

    with pytest.raises(RepositorioError):
        repo.guardar_fragmentos("otro-libro", [_fragmento("otro-libro", orden=1, id="debates_origen_01")])


def test_cambiar_fragmentos_de_libro_publicado_sube_la_version(repo):
    # Sin esto el MCP seguiría con el contenido viejo hasta reiniciarse.
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")
    antes = repo.version()

    repo.guardar_fragmentos("debates-origen", [_fragmento()])

    assert repo.version() == antes + 1


def test_reenviar_los_mismos_fragmentos_no_sube_la_version(repo):
    repo.guardar_libro(_libro())
    repo.publicar("debates-origen")
    repo.guardar_fragmentos("debates-origen", [_fragmento()])
    antes = repo.version()

    repo.guardar_fragmentos("debates-origen", [_fragmento()])

    assert repo.version() == antes


def test_cambiar_fragmentos_de_borrador_no_sube_la_version(repo):
    repo.guardar_libro(_libro())

    repo.guardar_fragmentos("debates-origen", [_fragmento()])

    assert repo.version() == 0


@pytest.mark.parametrize("id_inseguro", ['x" onmouseover="alert(1)', "-inicio", "con espacio"])
def test_fragmento_con_id_inseguro_no_se_construye(id_inseguro):
    with pytest.raises(ValidationError):
        _fragmento(id=id_inseguro)


@pytest.mark.parametrize("slug_invalido", ["Debates Origen", "debates_origen", "-debates"])
def test_libro_con_slug_invalido_no_se_construye(slug_invalido):
    with pytest.raises(ValidationError):
        _libro(slug_invalido)
