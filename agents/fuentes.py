"""Qué cuenta como fuente oficial y cómo se numeran las fuentes que ve el redactor."""
from urllib.parse import urlparse

# Dominios oficiales que no terminan en .gob.mx. Todo *.gob.mx entra solo.
OFICIALES_EXTRA = {
    "infonavit.org.mx",
    "inegi.org.mx",
    "ine.mx",
    "scjn.gob.mx",
    "dof.gob.mx",
    "imss.gob.mx",
    "cjf.gob.mx",
    "fgjcdmx.gob.mx",
}

# Ámbito → sitios donde busca. El orden importa: el primero es el más probable.
AMBITOS = {
    "federal": {
        "titulo": "Gobierno federal",
        "sitios": ["gob.mx", "sre.gob.mx", "sat.gob.mx", "imss.gob.mx", "infonavit.org.mx", "bienestar.gob.mx",
                   "stps.gob.mx", "profedet.gob.mx", "centrolaboral.gob.mx"],
    },
    "cdmx": {
        "titulo": "Ciudad de México",
        "sitios": ["cdmx.gob.mx", "fgjcdmx.gob.mx", "poderjudicialcdmx.gob.mx", "consejeria.cdmx.gob.mx",
                   "prosoc.cdmx.gob.mx"],
    },
    "justicia": {
        "titulo": "Leyes y justicia",
        "sitios": ["diputados.gob.mx", "scjn.gob.mx", "cjf.gob.mx", "dof.gob.mx", "congresocdmx.gob.mx"],
    },
}


def dominio(url_o_dominio: str) -> str:
    texto = url_o_dominio.strip().lower()
    if "://" in texto:
        texto = urlparse(texto).hostname or ""
    return texto.removeprefix("www.")


def es_oficial(url_o_dominio: str) -> bool:
    d = dominio(url_o_dominio)
    if not d:
        return False
    if d.endswith(".gob.mx") or d == "gob.mx":
        return True
    return any(d == o or d.endswith("." + o) for o in OFICIALES_EXTRA)


def texto_para_redactor(fuentes: list[dict]) -> str:
    """Lista numerada que el redactor cita como [n]. Nunca ve una URL que no venga de aquí."""
    if not fuentes:
        return "(no se encontró ninguna fuente oficial)"
    lineas = []
    for f in fuentes:
        lineas.append(f"[{f['n']}] {f['titulo']} ({f['dominio']})\n{f.get('fragmento', '').strip()[:900]}")
    return "\n\n".join(lineas)
