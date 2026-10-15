import pytest
from llm.catalog import ProviderId, catalogo_proveedores

NOMBRES = {ProviderId.LOCAL: "Local · llama3.2", ProviderId.CLOUD: "Nube · gpt-oss"}


def test_lista_todos_los_proveedores_del_enum_en_su_orden():
    catalogo = catalogo_proveedores(NOMBRES, registrados=[ProviderId.LOCAL])
    assert [info.id for info in catalogo] == list(ProviderId)


def test_disponible_solo_si_tiene_cliente_registrado():
    catalogo = catalogo_proveedores(NOMBRES, registrados=[ProviderId.LOCAL])
    assert {info.id: info.disponible for info in catalogo} == {ProviderId.LOCAL: True, ProviderId.CLOUD: False}


def test_proveedor_sin_nombre_falla_al_armar_el_catalogo():
    with pytest.raises(KeyError):
        catalogo_proveedores({ProviderId.LOCAL: "Local"}, registrados=[])
