"""Modo de ejecución.

vertex  : Cloud Run. Gemini en Vertex AI y la herramienta google_search de ADK.
gateway : servidor propio. Modelos por un gateway LiteLLM (API compatible con OpenAI) y búsqueda en SearXNG.
"""
import os

MODO = os.environ.get("TMX_MODO") or ("vertex" if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") else "gateway")

MODELO_VERTEX = os.environ.get("TMX_MODELO_VERTEX", "gemini-3.5-flash")
LITELLM_URL = os.environ.get("TMX_LITELLM_URL", "http://localhost:4000/v1")
SEARXNG_URL = os.environ.get("TMX_SEARXNG_URL", "http://localhost:8888")


def modelo(rol: str = "rapido"):
    """rol del gateway (rapido, razonar, veloz). En vertex todos son el mismo Gemini."""
    if MODO == "vertex":
        return MODELO_VERTEX
    from google.adk.models.lite_llm import LiteLlm

    os.environ.setdefault("LITELLM_TELEMETRY", "False")
    return LiteLlm(model="openai/" + rol, api_base=LITELLM_URL, api_key=os.environ.get("LITELLM_API_KEY", ""))
ROL_PLANEADOR = os.environ.get("TMX_ROL_PLANEADOR", "rapido")
ROL_RESUMEN = os.environ.get("TMX_ROL_RESUMEN", "rapido")
ROL_REDACTOR = os.environ.get("TMX_ROL_REDACTOR", "rapido")
