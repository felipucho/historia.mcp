import pytest

from agents.historian import EMPTY_ANSWER, HistorianAgent, MaxIterationsExceeded
from agents.prompt import build_system_prompt
from config import ROOT_DIR
from llm.provider import LLMResponse, LLMUnavailable, ToolCall
from store.history import render_documents, render_index
from tests.conftest import TOOL_NAME, FakeLLM, FakeTools
from tools.registry import ToolError, ToolsUnavailable


class _Statuses(list):
    async def __call__(self, state, tool):
        self.append((state, tool))


def _agent(llm, tools, system_prompt="SYSTEM", **kwargs) -> HistorianAgent:
    return HistorianAgent(llm, tools, system_prompt, **kwargs)


async def test_criterio_3_dabbene_dispara_tool_y_la_respuesta_la_incorpora(store):
    system_prompt = build_system_prompt(ROOT_DIR / "ia_config", render_index(store.documents))
    tool_output = render_documents(store.search("Lorenzo Dabbene").documents)
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME, arguments={"tema": "Lorenzo Dabbene"})]),
        LLMResponse(content="El registro no menciona a Lorenzo: corresponde a Valter Dabbene (teoría de 1903)."),
    ])
    tools = FakeTools({TOOL_NAME: tool_output})
    agent = _agent(llm, tools, system_prompt)
    conversation = agent.new_conversation()
    statuses = _Statuses()

    answer = await agent.run(conversation, "¿Quién es Lorenzo Dabbene?", statuses)

    assert "Valter Dabbene" in answer
    assert tools.calls == [(TOOL_NAME, {"tema": "Lorenzo Dabbene"})]
    assert tools.user_questions == ["¿Quién es Lorenzo Dabbene?"]  # viaja por _meta hasta la tool
    assert statuses == [("thinking", None), ("tool_call", TOOL_NAME), ("thinking", None)]
    second_call = llm.calls[1]
    system, *_, assistant, tool_message = second_call
    assert "mismo apellido" in system.content and system.content.rstrip().endswith("español.")
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == assistant.tool_calls[0].id
    assert "Valter Dabbene" in tool_message.content and "debates_origen_01" not in tool_message.content


async def test_contexto_conversacional_se_conserva_entre_turnos():
    llm = FakeLLM([LLMResponse(content="Respuesta 1"), LLMResponse(content="Respuesta 2")])
    agent = _agent(llm, FakeTools())
    conversation = agent.new_conversation()

    await agent.run(conversation, "pregunta 1", _Statuses())
    await agent.run(conversation, "pregunta 2", _Statuses())

    assert [(m.role, m.content) for m in llm.calls[1]] == [
        ("system", "SYSTEM"), ("user", "pregunta 1"), ("assistant", "Respuesta 1"), ("user", "pregunta 2"),
    ]


async def test_conversaciones_no_comparten_historial():
    llm = FakeLLM(lambda messages: LLMResponse(content="ok"))
    agent = _agent(llm, FakeTools())
    a, b = agent.new_conversation(), agent.new_conversation()

    await agent.run(a, "soy A", _Statuses())
    await agent.run(b, "soy B", _Statuses())

    assert [m.content for m in llm.calls[1]] == ["SYSTEM", "soy B"]
    assert (len(a), len(b)) == (1, 1)


async def test_ventana_de_historial_conserva_system_prompt():
    llm = FakeLLM(lambda messages: LLMResponse(content="r"))
    agent = _agent(llm, FakeTools(), max_turns=2)
    conversation = agent.new_conversation()

    for i in range(5):
        await agent.run(conversation, f"q{i}", _Statuses())

    last = llm.calls[-1]
    assert last[0].content == "SYSTEM"
    assert [m.content for m in last if m.role == "user"] == ["q2", "q3", "q4"]


async def test_tope_de_iteraciones():
    llm = FakeLLM(lambda messages: LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME, arguments={"tema": "x"})]))
    tools = FakeTools({TOOL_NAME: "nada"})
    agent = _agent(llm, tools, max_iterations=5)
    conversation = agent.new_conversation()

    with pytest.raises(MaxIterationsExceeded):
        await agent.run(conversation, "loop", _Statuses())
    assert len(llm.calls) == 5
    assert len(conversation) == 0  # turno fallido no ensucia el historial


async def test_sin_tools_no_consulta_al_modelo():
    llm = FakeLLM([])
    agent = _agent(llm, FakeTools(unavailable=True))

    with pytest.raises(ToolsUnavailable):
        await agent.run(agent.new_conversation(), "¿Quién es Dabbene?", _Statuses())
    assert llm.calls == []


async def test_error_de_tool_vuelve_al_modelo():
    class BrokenTools(FakeTools):
        async def call(self, name, arguments, *, user_question=None):
            raise ToolError("tema demasiado largo")

    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME, arguments={"tema": "x" * 500})]),
        LLMResponse(content="Reintento fallido, no tengo datos."),
    ])
    agent = _agent(llm, BrokenTools())
    answer = await agent.run(agent.new_conversation(), "x", _Statuses())

    assert answer == "Reintento fallido, no tengo datos."
    assert llm.calls[1][-1].content.startswith("ERROR de herramienta")


async def test_error_del_llm_no_deja_turno_a_medias():
    llm = FakeLLM([LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME)]), LLMUnavailable("caído")])
    agent = _agent(llm, FakeTools({TOOL_NAME: "datos"}))
    conversation = agent.new_conversation()

    with pytest.raises(LLMUnavailable):
        await agent.run(conversation, "x", _Statuses())
    assert len(conversation) == 0


async def test_respuesta_vacia():
    agent = _agent(FakeLLM([LLMResponse(content="   ")]), FakeTools())
    assert await agent.run(agent.new_conversation(), "x", _Statuses()) == EMPTY_ANSWER
