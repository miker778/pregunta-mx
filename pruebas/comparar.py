"""Compara dos servicios con las mismas preguntas: tiempo al resumen, total, fuentes y pasos.

Uso: .venv/bin/python pruebas/comparar.py URL_A URL_B
"""
import json
import sys
import time
from pathlib import Path

import httpx

PREGUNTAS = [
    "¿Cómo sé si mi patrón está pagando mi IMSS?",
    "Mi patrón me pide trabajar los sábados a las 10 pm sin pagarme horas extra, ¿dónde me quejo?",
    "¿Cómo hago un amparo?",
    "Me aumentaron la renta sin previo aviso, ¿qué puedo hacer?",
    "¿Cómo saco mi pasaporte?",
    "¿Qué hago si me robaron en mi casa?",
]
SALIDA = Path(__file__).parent / "salida" / "comparar"
SALIDA.mkdir(parents=True, exist_ok=True)


def correr(url: str, q: str) -> dict:
    t0, r = time.time(), {"resumen_s": None}
    with httpx.stream("POST", f"{url}/api/preguntar", json={"pregunta": q}, timeout=180) as resp:
        for linea in resp.iter_lines():
            o = json.loads(linea)
            if o["tipo"] == "resumen" and r["resumen_s"] is None:
                r["resumen_s"] = round(time.time() - t0, 1)
            if o["tipo"] == "respuesta":
                d = o["datos"]
                r.update(total_s=round(time.time() - t0, 1), fuentes=len(d["fuentes"]), pasos=len(d["pasos"]),
                         sin_fuente=d["sin_fuente"], datos=d)
            if o["tipo"] == "error":
                r.update(error=o.get("detalle"))
    return r


filas = {}
for etiqueta, url in (("A", sys.argv[1]), ("B", sys.argv[2])):
    for i, q in enumerate(PREGUNTAS):
        r = correr(url, q)
        (SALIDA / f"{etiqueta}-{i}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
        filas.setdefault(q, {})[etiqueta] = r
        print(f"{etiqueta} resumen {r['resumen_s']}s total {r.get('total_s')}s fuentes {r.get('fuentes')} pasos {r.get('pasos')}"
              f"{' ERROR ' + str(r['error']) if r.get('error') else ''}  {q[:50]}", flush=True)
        time.sleep(4)

def media(et, k):
    v = [f[et][k] for f in filas.values() if f[et].get(k) is not None]
    return round(sum(v) / len(v), 1) if v else None

for et in ("A", "B"):
    ok = sum(1 for f in filas.values() if not f[et].get("error") and f[et].get("fuentes", 0) >= 2 and f[et].get("pasos", 0) >= 1)
    print(f"{et}: resumen medio {media(et, 'resumen_s')}s, total medio {media(et, 'total_s')}s, completas {ok}/{len(filas)}")
