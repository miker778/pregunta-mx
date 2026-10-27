"""Pregunta MX: planeador → buscadores en paralelo → redactor, con Google ADK.

El redactor cita fuentes por número; la URL siempre la pone el código, nunca el modelo.
"""
import asyncio
import json
import re
from typing import AsyncGenerator

import httpx
from pydantic import BaseModel, Field
from google.adk.agents import BaseAgent, LlmAgent, ParallelAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from . import config
from .fuentes import AMBITOS, dominio, es_oficial, texto_para_redactor

POR_AMBITO = 6  # fuentes máximas por ámbito


# ---------- planeador ----------

PLANEADOR = """Eres el planeador de Pregunta MX, un asistente que explica trámites del gobierno de México
(federal y Ciudad de México) en español claro.

La persona escribe su situación con sus palabras. Tú NO contestas: decides qué buscar.

Devuelve SOLO un JSON, sin texto alrededor, con esta forma:
{"fuera_de_tema": false,
 "tema": "frase corta de lo que necesita",
 "consultas": {"federal": ["..."], "cdmx": ["..."], "justicia": ["..."]}}

Reglas:
- federal: trámites y programas del gobierno federal (SRE, SAT, IMSS, Infonavit, Bienestar, INM) y derechos laborales
  (STPS, PROFEDET, Centro Federal de Conciliación y Registro Laboral, Ley Federal del Trabajo).
- cdmx: trámites de la Ciudad de México y sus alcaldías (Registro Civil CDMX, Locatel 0311, Fiscalía FGJCDMX,
  Registro Público de la Propiedad, predial, tenencia, Procuraduría Social, arrendamiento, bacheo, Centro de
  Conciliación Laboral de la CDMX).
- justicia: leyes, juicios, amparos, defensoría pública, derechos (Cámara de Diputados, SCJN, Poder Judicial).
- Máximo 3 consultas por ámbito, cada una de 3 a 8 palabras, como se buscaría en Google. Lista vacía si el ámbito
  no aplica.
- Si la pregunta no tiene que ver con gobierno, trámites, programas, leyes o derechos, pon "fuera_de_tema": true.
"""


def _json_de(texto) -> dict:
    if isinstance(texto, dict):  # con output_schema, ADK ya lo guarda como dict
        return texto
    texto = (texto or "").strip()
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError("el modelo no devolvió JSON")
    crudo = m.group(0)
    try:
        return json.loads(crudo)
    except json.JSONDecodeError:
        # Reparación conocida: "fuentes": [1], [3], [5]  →  "fuentes": [1, 3, 5]
        reparado = re.sub(r'("fuentes"\s*:\s*)((?:\[\s*\d+\s*\]\s*,\s*)+\[\s*\d+\s*\])',
                          lambda mm: mm.group(1) + "[" + ", ".join(re.findall(r"\d+", mm.group(2))) + "]", crudo)
        return json.loads(reparado)


def planeador() -> LlmAgent:
    return LlmAgent(
        name="planeador",
        model=config.modelo(config.ROL_PLANEADOR),
        instruction=PLANEADOR,
        output_key="plan_texto",
    )


# ---------- buscadores: modo gateway (SearXNG local) ----------

async def _searxng(cli: httpx.AsyncClient, consulta: str) -> list[dict]:
    try:
        r = await cli.get(f"{config.SEARXNG_URL}/search", params={"q": consulta, "format": "json", "language": "es-MX"})
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception:
        return []


class BuscadorLocal(BaseAgent):
    """Corre todas las consultas del plan en paralelo contra SearXNG, solo dominios oficiales."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        plan = ctx.session.state.get("plan", {})
        pregunta = ctx.session.state.get("pregunta", "").lower()
        trabajos = []
        for ambito, consultas in (plan.get("consultas") or {}).items():
            if ambito not in AMBITOS or not consultas:
                continue
            sitio = "cdmx.gob.mx" if ambito == "cdmx" else "gob.mx"
            for c in consultas[:2]:
                trabajos.append((ambito, f"{c} site:{sitio}"))
            # SearXNG a veces ignora site:, así que la primera consulta va también con la palabra del dominio.
            c0 = consultas[0]
            trabajos.append((ambito, f"{c0} {'CDMX gob.mx' if ambito == 'cdmx' else 'gob.mx'}"))
            if ambito == "cdmx":
                trabajos.append((ambito, f"{c0} site:congresocdmx.gob.mx"))
            if ambito == "federal" and ("infonavit" in pregunta or "infonavit" in c0.lower()):
                trabajos.append((ambito, f"{c0} Infonavit infonavit.org.mx"))
            if ambito == "justicia":
                trabajos.append((ambito, f"{c0} site:scjn.gob.mx"))
        async with httpx.AsyncClient(timeout=5) as cli:  # una consulta lenta no frena a las demás
            resultados = await asyncio.gather(*[_searxng(cli, q) for _, q in trabajos])

        vistos, por_ambito = set(), {a: [] for a in AMBITOS}
        # Por turnos: el 1.º resultado de cada consulta, luego el 2.º, etc. Así cada consulta aporta y la
        # primera no llena sola el cupo del ámbito.
        filas = max((len(res) for res in resultados), default=0)
        en_orden = [(trabajos[i][0], resultados[i][k]) for k in range(filas)
                    for i in range(len(trabajos)) if k < len(resultados[i])]
        for ambito, r in en_orden:
            url = r.get("url", "")
            if not es_oficial(url) or url in vistos or len(por_ambito[ambito]) >= POR_AMBITO:
                continue
            vistos.add(url)
            por_ambito[ambito].append({
                "url": url,
                "titulo": (r.get("title") or dominio(url)).strip(),
                "dominio": dominio(url),
                "fragmento": (r.get("content") or "").strip(),
                "ambito": ambito,
            })
        fuentes = _numerar(por_ambito)
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
                    actions=EventActions(state_delta={"fuentes": fuentes}))


def _numerar(por_ambito: dict[str, list[dict]]) -> list[dict]:
    fuentes, n = [], 1
    for ambito in AMBITOS:
        for f in por_ambito.get(ambito, []):
            fuentes.append({**f, "n": n})
            n += 1
    return fuentes


# ---------- buscadores: modo vertex (google_search de ADK) ----------

def _guardar_grounding(ambito: str):
    """after_model_callback: guarda las fuentes reales que Google Search usó, con el texto que respaldan."""

    def cb(callback_context, llm_response):
        gm = getattr(llm_response, "grounding_metadata", None)
        if not gm or not gm.grounding_chunks:
            return None
        chunks = []
        for ch in gm.grounding_chunks:
            web = getattr(ch, "web", None)
            if web and web.uri:
                chunks.append({"url": web.uri, "titulo": web.title or "", "dominio": dominio(web.title or web.uri),
                               "fragmento": "", "ambito": ambito})
        for sup in gm.grounding_supports or []:
            texto = sup.segment.text if sup.segment else ""
            for i in sup.grounding_chunk_indices or []:
                if i < len(chunks) and texto:
                    chunks[i]["fragmento"] += texto + " "
        previas = callback_context.state.get(f"grounding_{ambito}", [])
        callback_context.state[f"grounding_{ambito}"] = previas + chunks
        return None

    return cb


def _buscador_vertex(ambito: str) -> LlmAgent:
    from google.adk.tools import google_search

    sitios = ", ".join(AMBITOS[ambito]["sitios"])

    def instruccion(ctx) -> str:
        consultas = (ctx.state.get("plan", {}).get("consultas") or {}).get(ambito) or []
        if not consultas:
            return "No hay nada que buscar en este ámbito. Responde solo: (sin búsqueda)"
        return (f"Busca con google_search, solo en sitios oficiales del gobierno de México ({sitios}), "
                f"estas consultas: {consultas}. Resume en español lo que dicen las fuentes oficiales: requisitos, "
                "pasos, costos con su año, dónde se hace y formularios. No uses blogs ni gestores.")

    return LlmAgent(name=f"buscador_{ambito}", model=config.modelo(), instruction=instruccion,
                    tools=[google_search], after_model_callback=_guardar_grounding(ambito))


class UnirGrounding(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        por_ambito = {}
        for ambito in AMBITOS:
            vistos, lista = set(), []
            for f in ctx.session.state.get(f"grounding_{ambito}", []):
                if es_oficial(f["dominio"]) and f["url"] not in vistos and len(lista) < POR_AMBITO:
                    vistos.add(f["url"])
                    lista.append(f)
            por_ambito[ambito] = lista
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
                    actions=EventActions(state_delta={"fuentes": _numerar(por_ambito)}))


# ---------- leer el plan del planeador ----------

class LeerPlan(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        try:
            plan = _json_de(ctx.session.state.get("plan_texto", ""))
        except Exception:
            plan = {"fuera_de_tema": False, "tema": "", "consultas": {"federal": [ctx.session.state.get("pregunta", "")]}}
        if plan.get("fuera_de_tema"):
            ctx.end_invocation = True
        yield Event(author=self.name, invocation_id=ctx.invocation_id,
                    actions=EventActions(state_delta={"plan": plan}))


# ---------- redactor ----------

REDACTOR = """Eres el redactor de Pregunta MX. Explicas trámites de México en español claro y sencillo.
No eres un sitio del gobierno.

Pregunta de la persona:
{pregunta}

Fuentes oficiales encontradas (solo puedes usar estas, cítalas por número):
{fuentes}

Otro agente ya escribe el resumen; tú solo das el detalle. Devuelve SOLO un JSON con esta forma:
{{"pasos": [{{"titulo": "verbo + qué", "detalle": "una frase", "fuentes": [n]}}],
 "documentos": [{{"texto": "qué llevar", "fuentes": [n]}}],
 "lugares": [{{"nombre": "oficina, sitio o teléfono", "detalle": "cómo sacar cita o cómo llegar", "fuentes": [n]}}],
 "costos": [{{"concepto": "...", "monto": "$ en pesos", "vigencia": "año", "fuentes": [n]}}],
 "formularios": [{{"nombre": "nombre del formato o solicitud", "fuentes": [n]}}],
 "avisos": ["advertencias útiles: es gratis, no necesitas gestor, cuidado con páginas falsas, plazos"],
 "nivel": ["federal" | "cdmx" | "alcaldia"]}}

Reglas:
- Cada dato concreto (requisito, costo, lugar, plazo) lleva al menos una fuente [n] de la lista. Si no está en las
  fuentes, no lo pongas. No inventes montos ni direcciones.
- Si las fuentes no alcanzan para contestar, deja las listas vacías.
- Entre 3 y 5 pasos, en orden. Máximo 3 avisos. Listas vacías si no aplican.
- Costos siempre con su año de vigencia, como lo diga la fuente.
- Si el trámite es gratis o hay riesgo de fraude o gestores, dilo en avisos.
- Español de México, frases cortas, sin tecnicismos legales sin explicar. Sin saludos.
- Cita así: [1][3], nunca [1, 3].
- Supón que la persona vive en la Ciudad de México, salvo que diga otro estado: usa fuentes federales y de la CDMX e ignora las de otros estados.
- Ojo con fuentes viejas: un PDF suelto, una página sin fecha o de años anteriores puede estar desactualizada.
  Si un requisito solo viene de una fuente así, o dos fuentes se contradicen, no lo presentes como seguro: dilo en
  avisos («esta fuente puede estar desactualizada, confirma en la oficina») y prefiere la ficha de trámite vigente.
"""


class _Paso(BaseModel):
    titulo: str
    detalle: str
    fuentes: list[int] = Field(default_factory=list)


class _Documento(BaseModel):
    texto: str
    fuentes: list[int] = Field(default_factory=list)


class _Lugar(BaseModel):
    nombre: str
    detalle: str = ""
    fuentes: list[int] = Field(default_factory=list)


class _Costo(BaseModel):
    concepto: str
    monto: str
    vigencia: str = ""
    fuentes: list[int] = Field(default_factory=list)


class _Formulario(BaseModel):
    nombre: str
    fuentes: list[int] = Field(default_factory=list)


class Detalle(BaseModel):
    """Forma fija de la salida del redactor: el modelo no puede devolver JSON roto."""
    pasos: list[_Paso] = Field(default_factory=list)
    documentos: list[_Documento] = Field(default_factory=list)
    lugares: list[_Lugar] = Field(default_factory=list)
    costos: list[_Costo] = Field(default_factory=list)
    formularios: list[_Formulario] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    nivel: list[str] = Field(default_factory=list)


def redactor() -> LlmAgent:
    def instruccion(ctx) -> str:
        return REDACTOR.format(pregunta=ctx.state.get("pregunta", ""),
                               fuentes=texto_para_redactor(ctx.state.get("fuentes", [])))

    return LlmAgent(name="redactor", model=config.modelo(config.ROL_REDACTOR), instruction=instruccion,
                    include_contents="none", output_schema=Detalle, output_key="respuesta_texto")


RESUMIDOR = """Eres Pregunta MX. Explicas trámites de México en español claro y sencillo. No eres un sitio
del gobierno.

Pregunta de la persona:
{pregunta}

Fuentes oficiales encontradas (solo puedes usar estas, cítalas por número):
{fuentes}

Supón que la persona vive en la Ciudad de México, salvo que diga otro estado: usa fuentes federales y de la CDMX e
ignora las de otros estados.

Escribe SOLO el resumen: 2 a 4 frases directas que contestan la pregunta, con citas [n] a las fuentes. Sin títulos,
sin listas, sin JSON, sin saludar. Cita así: [1][3], nunca [1, 3]. Si las fuentes no alcanzan para contestar, dilo en una frase. No inventes montos ni requisitos.
Si una fuente parece vieja o dos se contradicen, dilo.
"""


def resumidor() -> LlmAgent:
    def instruccion(ctx) -> str:
        return RESUMIDOR.format(pregunta=ctx.state.get("pregunta", ""),
                                fuentes=texto_para_redactor(ctx.state.get("fuentes", [])))

    return LlmAgent(name="resumidor", model=config.modelo(config.ROL_RESUMEN), instruction=instruccion,
                    include_contents="none", output_key="resumen_texto")


# ---------- todo junto ----------

def construir() -> SequentialAgent:
    if config.MODO == "vertex":
        buscar = SequentialAgent(name="busqueda", sub_agents=[
            ParallelAgent(name="buscadores", sub_agents=[_buscador_vertex(a) for a in AMBITOS]),
            UnirGrounding(name="unir_fuentes"),
        ])
    else:
        buscar = BuscadorLocal(name="buscador")
    return SequentialAgent(name="pregunta_mx", sub_agents=[
        planeador(), LeerPlan(name="leer_plan"), buscar,
        # El resumen llega primero a la pantalla; el detalle se escribe al mismo tiempo.
        ParallelAgent(name="redaccion", sub_agents=[resumidor(), redactor()]),
    ])
