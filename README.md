# Pregunta MX

Trámites de México en español claro, solo con fuentes oficiales.

Escribes lo que te está pasando, con tus palabras, y te contesta qué trámites siguen, en qué orden, qué llevar, a
dónde ir y cuánto cuesta. Cada dato lleva su liga a una fuente oficial (`*.gob.mx`). No pide cuenta ni CURP y no
guarda nada.

En vivo: https://mx.nostris.tech

No es un sitio del gobierno. Puede equivocarse: confirma en la fuente oficial. Orientación gratuita: Locatel
55 5658 1111 (CDMX) o 079 (federal).

**English.** Pregunta MX answers questions about Mexican government procedures in plain Spanish, using only official
sources. A Google ADK multi-agent pipeline plans the search, queries federal, Mexico City and justice sites in
parallel with Gemini and Google Search grounding, and writes a structured answer where every fact cites an official
source. Safety rules are enforced in code: the model never writes a URL, unsourced facts are dropped, off-topic
questions are refused, and nothing is stored. Built with Google ADK, Gemini 3.5 Flash Lite, FastAPI and Cloud Run.

## Por qué

- 4 de cada 10 trámites tienen algún problema; 15.6 % de quienes hicieron un trámite vivieron corrupción, con un
  costo de 17,707 millones de pesos ([INEGI, ENCIG 2025](https://www.inegi.org.mx/contenidos/saladeprensa/boletines/2026/encig/ENCIG2025_RR.pdf)).
- Hay 5,594 trámites federales (ATDT, junio 2026). Saber los pasos antes de ir evita la vuelta en balde y el gestor.

## Cómo funciona

```
pregunta ──▶ planeador (LlmAgent) ──▶ leer_plan ──▶ búsqueda ──▶ redacción ──▶ armar (código)
                                                                    ├─ resumidor (llega primero a la pantalla)
                                                                    └─ redactor (output_schema: JSON fijo)
                decide qué buscar       JSON         │              cita por número [n]     valida citas, pone URLs,
                por ámbito                           │                                       tira lo que no es oficial
                                                     ▼
                            vertex : ParallelAgent ─┬─ buscador_federal  (google_search)
                                                    ├─ buscador_cdmx     (google_search)
                                                    └─ buscador_justicia (google_search)
                                                    + unir_fuentes (grounding de Google, solo dominios oficiales)
                            gateway: buscador en paralelo contra SearXNG (site:gob.mx)
```

Candados (en código, no en el prompt):

- El modelo nunca escribe una URL. Cita `[n]` y el código pone la liga de la fuente real que encontró la búsqueda.
- Citas a fuentes que no existen se borran; pasos, costos y lugares sin fuente oficial se caen.
- Sin fuente oficial: «no sé» y Locatel 55 5658 1111 / 079.
- Fuera de tema: se rechaza.
- Nada se guarda: la sesión de ADK vive en memoria y se borra al terminar la respuesta. 8 preguntas por minuto por IP
  y 40 por minuto en total.
- Costos siempre con su año; fuentes viejas o que se contradicen generan un aviso.

Costo medido: unos 0.002 USD por pregunta con Gemini 3.5 Flash Lite; resumen en unos 4 s y respuesta completa en
unos 5 s.

## Modos

| Modo | Dónde | Modelo | Búsqueda |
|---|---|---|---|
| `vertex` | Cloud Run | Gemini en Vertex AI (`gemini-3.5-flash-lite`) | `google_search` de ADK |
| `gateway` | servidor propio | cualquier modelo detrás de un gateway LiteLLM | SearXNG |

## Desplegar en Cloud Run

Desde una máquina con `gcloud` autenticado:

```bash
git clone https://github.com/miker778/pregunta-mx && cd pregunta-mx
./deploy.sh            # usa el proyecto activo de gcloud; o ./deploy.sh <proyecto>
```

Habilita Run, Cloud Build y Vertex AI, despliega `pregunta-mx` en `us-central1`, prueba `/salud` y una pregunta, e
imprime la URL. Si Vertex dice que el modelo no existe en `global`, usa `UBICACION_MODELO=us-central1 ./deploy.sh`
o `MODELO=gemini-3.5-flash ./deploy.sh`.

## Correr local

```bash
uv venv && uv pip install -r pyproject.toml
# Con Vertex (gcloud auth application-default login):
GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=<proyecto> GOOGLE_CLOUD_LOCATION=global TMX_MODO=vertex \
  TMX_MODELO_VERTEX=gemini-3.5-flash-lite .venv/bin/uvicorn app.main:app --port 8080
```

## Pruebas

```bash
.venv/bin/python pruebas/test_vertex.py   # sin red: arma el modo vertex y prueba los candados de citas
.venv/bin/python pruebas/correr.py        # los ejemplos de la página + una fuera de tema, contra el servicio
pruebas/una.sh "¿Cómo hago un amparo?"     # una pregunta, legible
```

## Archivos

- `agents/agente.py`: el pipeline de ADK.
- `agents/fuentes.py`: qué dominio es oficial y en qué sitios busca cada ámbito.
- `agents/respuesta.py`: valida la salida del redactor.
- `app/main.py`: FastAPI, `POST /api/preguntar` en NDJSON (etapas y respuesta).
- `app/static/`: la página (sin build).

## Licencia

Código bajo [Apache 2.0](LICENSE). Hecho por ciudadanos, con [Nostris](https://nostris.tech), con Google ADK y
Claude Code.
