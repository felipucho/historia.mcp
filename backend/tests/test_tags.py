from store.repository import Fragmento
from store.tags import normalizar_tags


def test_criterio_a2_tags_quedan_normalizados():
    assert normalizar_tags(["Ferrocarril", " ferrocarril ", "Estación"]) == ["ferrocarril", "estacion"]


def test_descarta_vacios_y_repetidos_despues_de_normalizar():
    assert normalizar_tags(["  ", "Fundación", "fundacion", "", "FUNDACIÓN"]) == ["fundacion"]


def test_colapsa_espacios_internos():
    assert normalizar_tags(["  Ferrocarril   del\tSur "]) == ["ferrocarril del sur"]


def test_conserva_el_orden_de_primera_aparicion():
    assert normalizar_tags(["poblacion", "origen", "Poblacion"]) == ["poblacion", "origen"]


def test_la_enie_pierde_la_tilde_como_en_la_busqueda():
    # Mismo criterio que store.history.normalize: la búsqueda y los tags comparan igual.
    assert normalizar_tags(["Año"]) == ["ano"]


def test_es_idempotente():
    una_vez = normalizar_tags(["Ferrocarril", "Estación"])

    assert normalizar_tags(una_vez) == una_vez


def test_fragmento_normaliza_sus_tags_al_construirse():
    fragmento = Fragmento(id="x_01", libro_slug="x", orden=1, titulo="t", contenido="c", tags=["Estación"])

    assert fragmento.tags == ["estacion"]
