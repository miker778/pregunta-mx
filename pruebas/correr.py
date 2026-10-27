"""Set de prueba: cada ejemplo de la página debe traer ≥2 fuentes oficiales; lo fuera de tema se rechaza.

Uso: .venv/bin/python pruebas/correr.py [URL]   (por defecto http://localhost:8080)
"""
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agents.fuentes import es_oficial  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
JS = (Path(__file__).resolve().parents[1] / "app/static/app.js").read_text()
EJEMPLOS = re.findall(r'\["(?:trabajo|federal|cdmx|justicia|vivienda)", "([^"]+)"\]', JS)
FUERA = ["Dame una receta de pozole rojo"]
SALIDA = Path(__file__).parent / "salida"
SALIDA.mkdir(exist_ok=True)


def preguntar(q: str) -> dict:
    with httpx.stream("POST", f"{URL}/api/preguntar", json={"pregunta": q}, timeout=240) as r:
        r.raise_for_status()
        for linea in r.iter_lines():
            o = json.loads(linea)
            if o["tipo"] == "respuesta":
                return o["datos"]
            if o["tipo"] == "error":
                return {"error": o.get("detalle", "?")}
    return {"error": "sin respuesta"}


fallas, filas = 0, []
for q in EJEMPLOS + FUERA:
    t = time.time()
    d = preguntar(q)
    (SALIDA / (re.sub(r"\W+", "-", q.lower()).strip("-")[:60] + ".json")).write_text(json.dumps(d, ensure_ascii=False, indent=1))
    if q in FUERA:
        ok = d.get("sin_fuente") is True and not d.get("fuentes")
        motivo = "rechazada" if ok else "debió rechazarse"
    else:
        fuentes = d.get("fuentes", [])
        oficiales = all(es_oficial(f["url"]) for f in fuentes)
        ok = "error" not in d and len(fuentes) >= 2 and oficiales and not d.get("sin_fuente")
        motivo = f"{len(fuentes)} fuentes, {len(d.get('pasos', []))} pasos" if "error" not in d else d["error"]
    fallas += not ok
    filas.append(f"{'OK ' if ok else 'MAL'} {time.time() - t:5.1f}s  {q}  ({motivo})")
    print(filas[-1], flush=True)
    time.sleep(8)  # el límite es 8 por minuto por IP

print(f"\n{len(filas) - fallas}/{len(filas)} pasan")
sys.exit(1 if fallas else 0)
