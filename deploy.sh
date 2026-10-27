#!/usr/bin/env bash
# Despliega Pregunta MX en Cloud Run desde una máquina con gcloud ya autenticado.
# Uso: ./deploy.sh [proyecto]   (por defecto el proyecto activo de gcloud)
set -euo pipefail
PROYECTO="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
UBICACION_MODELO="${UBICACION_MODELO:-global}"
# Flash Lite: rápido (unos 5 s por respuesta). Si Vertex no lo acepta con google_search,
# vuelve a correr con MODELO=gemini-3.5-flash ./deploy.sh
MODELO="${MODELO:-gemini-3.5-flash-lite}"
[ -n "$PROYECTO" ] || { echo "Falta el proyecto: ./deploy.sh <proyecto>"; exit 1; }

gcloud services enable run.googleapis.com cloudbuild.googleapis.com aiplatform.googleapis.com --project "$PROYECTO"
gcloud run deploy pregunta-mx \
  --project "$PROYECTO" --region "$REGION" --source . \
  --allow-unauthenticated --memory 1Gi --cpu 1 --timeout 300 --max-instances 3 --concurrency 20 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROYECTO,GOOGLE_CLOUD_LOCATION=$UBICACION_MODELO,GOOGLE_GENAI_USE_VERTEXAI=TRUE,TMX_MODO=vertex,TMX_MODELO_VERTEX=$MODELO"

URL=$(gcloud run services describe pregunta-mx --project "$PROYECTO" --region "$REGION" --format 'value(status.url)')
echo "Salud:"; curl -s "$URL/salud"; echo
echo "Prueba:"; PRUEBA=$(curl -s -X POST "$URL/api/preguntar" -H 'content-type: application/json' \
  -d '{"pregunta":"¿Cómo saco mi pasaporte?"}' | tail -1)
echo "$PRUEBA" | cut -c1-400; echo
echo "$PRUEBA" | grep -q '"tipo": "respuesta"' || echo "La prueba no trajo respuesta. Si el modelo no existe en Vertex: MODELO=gemini-3.5-flash ./deploy.sh"
echo "Listo: $URL"
