import pytest
from llm.provider import InvalidToolCall
from llm.wire import tool_call_from_wire


def test_arguments_como_string_json_y_como_objeto():
    as_string = tool_call_from_wire({"id": "c1", "function": {"name": "buscar", "arguments": '{"tema": "x"}'}})
    as_object = tool_call_from_wire({"function": {"name": "buscar", "arguments": {"tema": "x"}}})
    assert (as_string.id, as_string.arguments) == ("c1", {"tema": "x"})
    assert as_object.arguments == {"tema": "x"}
    assert as_object.id.startswith("call_")


@pytest.mark.parametrize("arguments", [None, "", {}])
def test_arguments_vacios_son_objeto_vacio(arguments):
    assert tool_call_from_wire({"function": {"name": "buscar", "arguments": arguments}}).arguments == {}


@pytest.mark.parametrize(
    "raw",
    [
        "no es un dict",
        {"function": {"arguments": {}}},
        {"function": {"name": "", "arguments": {}}},
        {"function": {"name": "buscar", "arguments": "{roto"}},
        {"function": {"name": "buscar", "arguments": "[1, 2]"}},
    ],
)
def test_tool_call_invalido_lanza_invalid_tool_call(raw):
    with pytest.raises(InvalidToolCall):
        tool_call_from_wire(raw)
