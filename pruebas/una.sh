#!/usr/bin/env bash
# Uso: pruebas/una.sh "pregunta"   (contra el servicio local localhost:8080)
curl -s -m 240 -X POST "${TMX_URL:-http://localhost:8080}/api/preguntar" -H 'content-type: application/json' \
  -d "$(python3 -c 'import json,sys; print(json.dumps({"pregunta": sys.argv[1]}))' "$1")" | python3 -c "
import sys,json
for l in sys.stdin:
  o=json.loads(l)
  if o['tipo']!='respuesta': print(o); continue
  d=o['datos']; print('RESUMEN:',d['resumen']); print('sin_fuente',d['sin_fuente'],'seg',d['segundos'])
  for k in ('pasos','documentos','lugares','costos','formularios'): print(' ',k,len(d[k]), [(i.get('titulo') or i.get('texto') or i.get('nombre') or i.get('concepto'), i.get('monto')) for i in d[k]][:5])
  print('  avisos',d['avisos']); [print('  ',f['n'],f['url']) for f in d['fuentes']]"
