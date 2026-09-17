"""Eval del agente contra Ollama real y el servidor MCP en memoria.

No corre en pytest: depende del modelo instalado y tarda minutos. Detecta regresiones de calidad
(alucinaciones, avisos falsos) que los tests con FakeLLM no ven.

Uso (desde backend/): python -m evals.eval_agent --reps 2 [--temperature 0.1] [--only valter,tren]
"""

import argparse
import asyncio
import logging
import re
import sys
from collections import Counter
from typing import Any

from agents.historian import HistorianAgent
from agents.prompt import build_system_prompt
from config import Settings
from llm.ollama import OllamaClient
from llm.provider import ToolSpec
from mcp_server import build_server
from store.history import HistoryStore, render_index
from tools.registry import McpToolRegistry, ToolRegistry

NO_INFO = r"no (tengo|cuento|dispongo|hay|encontr|figura|aparece)|sin informaci|no se menciona|no est[aá] (document|registr)"
SPECULATION = (
    r"\bhij[oa]\b|familia|pariente|herman|padre|madre|espos[oa]|casad|sobrin|abuel|niet[oa]|descendiente"
    r"|probablemente|es posible que(?! est[eé]s pensando)|podr[ií]a (ser|implicar|haber)|supuestamente|se supone"
    r"|pol[ií]tic|periodist|escritor|naci[oó]\b|nacid[oa]|argentin|publicad[oa]|public[oó]|Fundaci[oó]n Las Varillas"
)
FALSE_WARNING = r"no hay registros"

# nombre: [(pregunta, [regex requeridos], [regex prohibidos])]. Los turnos de un escenario comparten conversación.
SCENARIOS: dict[str, list[tuple[str, list[str], list[str]]]] = {
    "dabbene_seguimiento": [
        ("¿Quién es Lorenzo Dabbene?", [r"Valter", NO_INFO], [SPECULATION, r"Lorenzo Dabbene (es|fue) "]),
        ("¿Y qué fuente respalda esa postura?", [r"documentaci[oó]n municipal|registros oficiales|fuente[^.]*Valter Dabbene"], [SPECULATION, r"Lorenzo Dabbene (es|fue) "]),
        ("¿Y quién defiende la teoría de 1904?", [r"Alvarez|Álvarez"], [SPECULATION, r"Lorenzo Dabbene (es|fue) "]),
    ],
    "tren": [("¿Cuándo llegó el tren?", [r"1900", r"diciembre"], [])],
    "fundacion_debate": [("¿En qué año se fundó Las Varillas?", [r"1900", r"1903", r"1904"], [])],
    "valter": [("¿Quién es Valter Dabbene?", [r"historiador", r"1903"], [SPECULATION, r"Lorenzo", FALSE_WARNING])],
    "saludo_con_nombre": [("Hola, ¿quién es Valter Dabbene?", [r"historiador", r"1903"], [SPECULATION, FALSE_WARNING])],
    "fuera_de_datos": [("¿Quién fue el primer intendente de Las Varillas?", [NO_INFO], [SPECULATION])],
    "fuera_de_dominio": [("¿Quién ganó el mundial 2022?", [NO_INFO + r"|solo (puedo|te puedo)"], [r"Argentina|Messi|Francia"])],
    "saludo": [("Hola, ¿qué podés hacer?", [], [SPECULATION])],
    "general_historia": [("Contame la historia de Las Varillas", [r"1900|1903|1904"], [SPECULATION, FALSE_WARNING, r"San Juan"])],
    "general_sabes": [("¿Qué sabés de la historia de Las Varillas?", [r"1900|1903|1904"], [SPECULATION, FALSE_WARNING, r"San Juan"])],
    "juan_alvarez": [("¿Quién fue Juan Alvarez?", [NO_INFO, r"Alvarez|Álvarez"], [SPECULATION, r"Juan Alvarez (es|fue) "])],
    "anio_inexistente": [("¿Qué pasó en 1910 en Las Varillas?", [NO_INFO], [SPECULATION])],
    "opinion": [
        ("¿Cuáles son las teorías sobre la fundación?", [r"1900", r"1903", r"1904"], [SPECULATION]),
        ("¿Y cuál es la correcta?", [], [SPECULATION, r"la (teor[ií]a )?correcta es"]),
    ],
    "institucion": [("Contame sobre el Centro de Estudios Parada KM 81", [r"ferrocarril|1900"], [SPECULATION])],
    "anio_1904": [("¿Qué pasó en 1904?", [r"mensura|ejido|trazad"], [SPECULATION])],
}


class _RecordingTools(ToolRegistry):
    """Registra qué buscó el modelo y qué documentos volvieron, para leer los fallos."""

    def __init__(self, inner: ToolRegistry) -> None:
        self._inner = inner
        self.log: list[str] = []

    async def specs(self) -> list[ToolSpec]:
        return await self._inner.specs()

    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        result = await self._inner.call(name, arguments, user_question=user_question)
        hits = re.findall(r"^\[(\w+)\]", result, re.M)
        self.log.append(f"{arguments} -> {hits or result[:60].replace(chr(10), ' ')}")
        return result


async def _noop_status(state: str, tool: str | None) -> None:
    return None


async def run(scenarios: dict, repetitions: int, temperature: float | None) -> int:
    settings = Settings()
    store = HistoryStore.from_file(settings.data_file)
    temperature = settings.ollama_temperature if temperature is None else temperature
    print(f"modelo={settings.ollama_model} temperatura={temperature}")
    llm = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_model,
        num_ctx=settings.ollama_num_ctx,
        keep_alive=settings.ollama_keep_alive,
        connect_timeout=settings.ollama_connect_timeout,
        read_timeout=settings.ollama_read_timeout,
        temperature=temperature,
    )
    registry = McpToolRegistry(build_server(store), connect_timeout=20, call_timeout=15, retry_base=2, retry_max=60)
    tools = _RecordingTools(registry)
    agent = HistorianAgent(llm, tools, build_system_prompt(settings.ia_config_dir, render_index(store.documents)))
    failures: Counter[str] = Counter()
    total = 0
    try:
        for rep in range(1, repetitions + 1):
            print(f"\n=== repetición {rep} ===")
            for name, turns in scenarios.items():
                conversation = agent.new_conversation()
                for question, required, forbidden in turns:
                    tools.log.clear()
                    try:
                        answer = await agent.run(conversation, question, _noop_status)
                    except Exception as exc:  # noqa: BLE001 - un fallo del turno es un resultado del eval
                        answer = f"<<{type(exc).__name__}: {exc}>>"
                    problems = [f"falta /{r}/" for r in required if not re.search(r, answer, re.I)]
                    problems += [f"prohibido /{r}/" for r in forbidden if re.search(r, answer, re.I)]
                    total += 1
                    if problems:
                        failures[f"{name}: {question}"] += 1
                    print(f"[{'MAL' if problems else 'OK '}] ({name}) {question}  tools={tools.log}")
                    print(f"      {answer}")
                    if problems:
                        print(f"      -> {'; '.join(problems)}")
    finally:
        await registry.aclose()
        await llm.aclose()
    print(f"\n=== resumen: {total - sum(failures.values())}/{total} OK ===")
    for key, count in failures.most_common():
        print(f"  {count}x {key}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=None, help="por defecto OLLAMA_TEMPERATURE")
    parser.add_argument("--only", default="", help="escenarios separados por coma")
    args = parser.parse_args()
    wanted = {name for name in args.only.split(",") if name}
    if unknown := wanted - SCENARIOS.keys():
        parser.error(f"escenarios desconocidos: {', '.join(sorted(unknown))}")
    scenarios = {name: turns for name, turns in SCENARIOS.items() if not wanted or name in wanted}
    logging.disable(logging.CRITICAL)
    sys.exit(asyncio.run(run(scenarios, args.reps, args.temperature)))


if __name__ == "__main__":
    main()
