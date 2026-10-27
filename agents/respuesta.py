"""Convierte la salida del redactor en la respuesta final: valida citas y pone las URLs reales."""
import re

from .agente import _json_de

LISTAS = ("pasos", "documentos", "lugares", "costos", "formularios")
SIN_FUENTE = {
    "resumen": "No encontré una fuente oficial que conteste esto con seguridad. Para orientación gratuita llama a "
               "Locatel al 55 5658 1111 (CDMX) o al 079 (gobierno federal).",
    "pasos": [], "documentos": [], "lugares": [], "costos": [], "formularios": [],
    "avisos": [], "nivel": [],
}
FUERA_DE_TEMA = {
    **SIN_FUENTE,
    "resumen": "Solo contesto sobre trámites, programas, leyes y derechos ante el gobierno de México. "
               "Prueba con algo como «¿cómo saco mi pasaporte?».",
}


def normalizar_citas(texto: str) -> str:
    """[2, 3] o [2,3] → [2][3]: algunos modelos agrupan las citas."""
    return re.sub(r"\[(\d+(?:\s*,\s*\d+)+)\]", lambda m: "".join(f"[{n.strip()}]" for n in m.group(1).split(",")), texto or "")


def _citas(valor, validos: set[int]) -> list[int]:
    if isinstance(valor, int):
        valor = [valor]
    if not isinstance(valor, list):
        return []
    return [n for n in valor if isinstance(n, int) and n in validos]


def armar(texto_redactor: str, fuentes: list[dict], plan: dict, resumen: str | None = None) -> dict:
    if plan.get("fuera_de_tema"):
        return {**FUERA_DE_TEMA, "fuentes": [], "sin_fuente": True, "tema": ""}
    validos = {f["n"] for f in fuentes}
    try:
        crudo = _json_de(texto_redactor)
    except Exception:
        crudo = {}

    salida = {"tema": plan.get("tema", ""),
              "resumen": normalizar_citas(str(resumen if resumen is not None else crudo.get("resumen", ""))).strip()}
    for lista in LISTAS:
        limpios = []
        for item in crudo.get(lista) or []:
            if not isinstance(item, dict):
                continue
            citas = _citas(item.get("fuentes", item.get("fuente")), validos)
            if not citas:  # sin fuente oficial, fuera
                continue
            limpios.append({**{k: v for k, v in item.items() if k not in ("fuente",)}, "fuentes": citas})
        salida[lista] = limpios
    salida["avisos"] = [normalizar_citas(str(a)) for a in (crudo.get("avisos") or []) if str(a).strip()][:4]
    for lista in LISTAS:
        for item in salida[lista]:
            for k in ("detalle", "texto"):
                if isinstance(item.get(k), str):
                    item[k] = normalizar_citas(item[k])
    salida["nivel"] = [n for n in (crudo.get("nivel") or []) if n in ("federal", "cdmx", "alcaldia")]

    # Citas del resumen que no existan se quitan del texto.
    salida["resumen"] = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in validos else "",
                               salida["resumen"]).strip()

    usadas = set(re.findall(r"\[(\d+)\]", salida["resumen"]))
    usadas = {int(n) for n in usadas}
    for lista in LISTAS:
        for item in salida[lista]:
            usadas.update(item["fuentes"])
    salida["fuentes"] = [{k: f[k] for k in ("n", "url", "titulo", "dominio", "ambito")} for f in fuentes if f["n"] in usadas]

    if not salida["fuentes"] or not salida["resumen"]:
        return {**SIN_FUENTE, "tema": salida["tema"], "fuentes": [], "sin_fuente": True}
    salida["sin_fuente"] = False
    return salida


def limpiar_resumen(texto: str, fuentes: list[dict]) -> str:
    """El resumen que se manda antes del detalle: sin citas a fuentes que no existen."""
    validos = {f["n"] for f in fuentes}
    return re.sub(r"\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in validos else "",
                  normalizar_citas(texto).strip()).strip()
