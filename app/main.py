"""Pregunta MX: API + página. POST /api/preguntar devuelve NDJSON con etapas y la respuesta final.

Privacidad: no se guarda la pregunta ni la respuesta. La sesión de ADK vive en memoria y se borra al terminar.
"""
import json
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from agents import config
from agents.agente import construir
from agents.fuentes import AMBITOS
from agents.respuesta import armar, limpiar_resumen

APP = "pregunta_mx"
ESTATICO = Path(__file__).parent / "static"
POR_MINUTO = int(os.environ.get("TMX_POR_MINUTO", "8"))
TOTAL_POR_MINUTO = int(os.environ.get("TMX_TOTAL_POR_MINUTO", "40"))  # tope global por instancia: cuida el gasto
# Solo detrás de un túnel de Cloudflare se confía en CF-Connecting-IP. En Cloud Run nadie lo reescribe.
DETRAS_DE_CLOUDFLARE = os.environ.get("TMX_DETRAS_DE_CLOUDFLARE") == "1"

app = FastAPI(title="Pregunta MX")
app.mount("/static", StaticFiles(directory=ESTATICO), name="static")
sesiones = InMemorySessionService()
runner = Runner(app_name=APP, agent=construir(), session_service=sesiones)
_visitas: dict[str, deque] = defaultdict(deque)


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=3, max_length=500)
    contexto: str = Field(default="", max_length=2000)  # turnos previos del chat; vive solo en el navegador


def _ip(request: Request) -> str:
    """IP real sin confiar en lo que mande el cliente.

    Detrás del túnel de Cloudflare, Cloudflare reescribe CF-Connecting-IP en su borde. En Cloud Run, el frontend de
    Google agrega la IP real al final de X-Forwarded-For; lo que va antes lo pudo escribir el cliente.
    """
    cf = request.headers.get("cf-connecting-ip") if DETRAS_DE_CLOUDFLARE else None
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def _limite(ip: str) -> None:
    ahora = time.time()
    for clave, tope, aviso in ((ip, POR_MINUTO, "Demasiadas preguntas seguidas. Espera un minuto."),
                               ("*", TOTAL_POR_MINUTO, "Hay muchas preguntas en este momento. Intenta en un minuto.")):
        cola = _visitas[clave]
        while cola and ahora - cola[0] > 60:
            cola.popleft()
        if len(cola) >= tope:
            raise HTTPException(429, aviso)
    _visitas[ip].append(ahora)
    _visitas["*"].append(ahora)


def _version() -> str:
    """Cambia cada vez que cambia un archivo de la página, para que Cloudflare y el navegador no sirvan uno viejo."""
    return str(int(max(f.stat().st_mtime for f in ESTATICO.iterdir())))


@app.get("/")
def inicio():
    v = _version()
    html = (ESTATICO / "index.html").read_text().replace(".css\"", f".css?v={v}\"").replace(".js\"", f".js?v={v}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/salud")
def salud():
    return {"ok": True, "modo": config.MODO}


@app.post("/api/preguntar")
async def preguntar(p: Pregunta, request: Request):
    _limite(_ip(request))
    texto = p.pregunta.strip()
    if p.contexto.strip():
        texto = f"Conversación previa (solo para entender la pregunta nueva):\n{p.contexto.strip()}\n\nPregunta nueva: {texto}"
    return StreamingResponse(_correr(texto), media_type="application/x-ndjson")


def _linea(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode()


async def _correr(pregunta: str):
    usuario, sid = "anonimo", uuid.uuid4().hex
    await sesiones.create_session(app_name=APP, user_id=usuario, session_id=sid, state={"pregunta": pregunta})
    inicio = time.time()
    yield _linea({"tipo": "etapa", "texto": "Entendiendo tu pregunta"})
    try:
        async for ev in runner.run_async(user_id=usuario, session_id=sid,
                                         new_message=types.Content(role="user", parts=[types.Part(text=pregunta)])):
            delta = ev.actions.state_delta if ev.actions else {}
            if "plan" in delta:
                plan = delta["plan"]
                if plan.get("fuera_de_tema"):
                    continue
                donde = [AMBITOS[a]["titulo"] for a, c in (plan.get("consultas") or {}).items() if c and a in AMBITOS]
                yield _linea({"tipo": "etapa", "texto": "Buscando en fuentes oficiales: " + ", ".join(donde),
                              "t": round(time.time() - inicio, 1)})
            if "resumen_texto" in delta:
                estado = (await sesiones.get_session(app_name=APP, user_id=usuario, session_id=sid)).state
                fuentes = estado.get("fuentes", [])
                yield _linea({"tipo": "resumen", "texto": limpiar_resumen(delta["resumen_texto"], fuentes),
                              "fuentes": [{k: f[k] for k in ("n", "url", "titulo", "dominio")} for f in fuentes],
                              "t": round(time.time() - inicio, 1)})
            if "fuentes" in delta:
                yield _linea({"tipo": "etapa", "texto": f"Leyendo {len(delta['fuentes'])} páginas oficiales",
                              "t": round(time.time() - inicio, 1)})
        estado = (await sesiones.get_session(app_name=APP, user_id=usuario, session_id=sid)).state
        final = armar(estado.get("respuesta_texto", ""), estado.get("fuentes", []), estado.get("plan", {}),
                      estado.get("resumen_texto"))
        final["segundos"] = round(time.time() - inicio, 1)
        yield _linea({"tipo": "respuesta", "datos": final})
    except Exception as e:  # nunca devolvemos la pregunta en el error
        yield _linea({"tipo": "error", "texto": "Algo falló al buscar. Intenta de nuevo en un momento.",
                      "detalle": type(e).__name__})
    finally:
        await sesiones.delete_session(app_name=APP, user_id=usuario, session_id=sid)
