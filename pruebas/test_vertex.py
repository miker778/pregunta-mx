"""Prueba sin red del modo vertex: arma el agente y simula lo que devuelve Google Search.

Uso: TMX_MODO=vertex .venv/bin/python pruebas/test_vertex.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["TMX_MODO"] = "vertex"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google.genai import types  # noqa: E402

from agents import agente  # noqa: E402
from agents.respuesta import armar  # noqa: E402

raiz = agente.construir()
nombres = [a.name for a in raiz.sub_agents]
assert nombres == ["planeador", "leer_plan", "busqueda", "redaccion"], nombres
assert [a.name for a in raiz.sub_agents[3].sub_agents] == ["resumidor", "redactor"]
paralelo = raiz.sub_agents[2].sub_agents[0]
assert [b.name for b in paralelo.sub_agents] == ["buscador_federal", "buscador_cdmx", "buscador_justicia"]
for b in paralelo.sub_agents:
    assert len(b.tools) == 1 and type(b.tools[0]).__name__ == "GoogleSearchTool", b.tools
    assert b.model == "gemini-3.5-flash"

# Simula la respuesta de Gemini con grounding: una fuente oficial y una de un blog.
gm = types.GroundingMetadata(
    grounding_chunks=[
        types.GroundingChunk(web=types.GroundingChunkWeb(uri="https://vertexaisearch.cloud.google.com/redir/1", title="gob.mx")),
        types.GroundingChunk(web=types.GroundingChunkWeb(uri="https://vertexaisearch.cloud.google.com/redir/2", title="tramitesfaciles.com")),
    ],
    grounding_supports=[types.GroundingSupport(segment=types.Segment(text="El pasaporte de 3 años cuesta $1,795 en 2026."),
                                               grounding_chunk_indices=[0, 1])],
)
estado = {}
ctx = SimpleNamespace(state=estado)
agente._guardar_grounding("federal")(ctx, SimpleNamespace(grounding_metadata=gm))
assert len(estado["grounding_federal"]) == 2
assert "1,795" in estado["grounding_federal"][0]["fragmento"]

# Unir: el blog se cae, la oficial queda como [1].
por_ambito = {"federal": [f for f in estado["grounding_federal"] if agente.es_oficial(f["dominio"])]}
fuentes = agente._numerar(por_ambito)
assert [f["dominio"] for f in fuentes] == ["gob.mx"] and fuentes[0]["n"] == 1

# El redactor cita [1] y un [7] inventado: el [7] se borra, el costo sin fuente se cae.
salida = armar('{"resumen": "Cuesta $1,795 [1][7].", "costos": [{"concepto": "3 años", "monto": "$1,795", '
               '"vigencia": "2026", "fuentes": [1]}, {"concepto": "inventado", "monto": "$1", "fuentes": [9]}]}',
               fuentes, {"tema": "pasaporte"})
assert salida["resumen"] == "Cuesta $1,795 [1].", salida["resumen"]
assert len(salida["costos"]) == 1 and salida["fuentes"][0]["n"] == 1 and not salida["sin_fuente"]
assert armar("{}", [], {"fuera_de_tema": True})["sin_fuente"]
# El resumen viene del resumidor; el JSON del redactor ya no lo trae.
con_resumen = armar('{"pasos": [{"titulo": "Saca cita", "detalle": "En línea [1].", "fuentes": [1]}]}', fuentes, {}, "Sí se puede [1][4].")
assert con_resumen["resumen"] == "Sí se puede [1]." and len(con_resumen["pasos"]) == 1
print("modo vertex: 10/10 comprobaciones OK")
