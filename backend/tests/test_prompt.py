from agents.prompt import RULES
from mcp_meta import AVISO_PREFIJO


def test_regla_5_nombra_el_marcador_que_emite_la_tool():
    assert f"trae un {AVISO_PREFIJO}," in RULES
