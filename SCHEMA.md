# PathMind API — Schema Reference

## POST /api/analyze

Lance le pipeline d'analyse multi-agents. La réponse est immédiate (async) ; les résultats arrivent via WebSocket.

### Request body

```json
{
  "case_id": "string",          // identifiant unique du cas (ex: "case-2026-001")
  "patient_id": "string",       // identifiant patient (ex: "P001")
  "slide_paths": ["string"],    // liste de chemins vers les lames (ex: ["data/slides/A.svs"])
  "clinical_data": {}           // optionnel — données cliniques libres (âge, antécédents, etc.)
}
```

Champs obligatoires : `case_id`, `patient_id`, `slide_paths` (au moins 1 élément).

### Response body

```json
{
  "case_id": "string",    // echo du case_id
  "status": "started"     // toujours "started" — pipeline async
}
```

Le pipeline tourne en arrière-plan. Connectez-vous au WebSocket `/ws/{case_id}` avant ou après l'appel POST pour recevoir les events.

---

## WebSocket /ws/{case_id}

Stream temps réel des événements agents. Chaque message est un objet JSON.

### Format général d'un event

```json
{
  "agent": "string",           // nom de l'agent émetteur
  "status": "string",          // état : "running" | "done" | "started" | "complete"
  "content": "string",         // contenu textuel (résumé, JSON string, rapport)
  "confidence": 0.0,           // optionnel — score de confiance 0-1
  "slide": 0,                  // optionnel — index de lame concernée
  "timestamp": "ISO8601"       // horodatage UTC (présent si émis via AgentEvent schema)
}
```

### Types d'events par agent

#### pipeline (orchestrateur)

| status | content | notes |
|--------|---------|-------|
| `started` | "N lames" | 1er event, toujours émis |
| `complete` | texte du rapport final | dernier event, inclut `confidence` |

#### tile_triage

| status | content | champs extra |
|--------|---------|--------------|
| `running` | "Analyse lame N" | — |
| `done` | JSON string avec `regions_of_interest`, `tile_count`, `summary`, `confidence` | `slide: int` |

#### histopathologist

| status | content | champs extra |
|--------|---------|--------------|
| `running` | "Analyse histologique lame N" | `slide: int` |
| `done` | JSON string avec `findings`, `grade`, `mitotic_index`, `margin_status`, `confidence` | `slide: int` |

#### cross_slide_aggregator

| status | content |
|--------|---------|
| `running` | "Synthese N lames" |
| `done` | JSON string avec `synthesis`, `dominant_pattern`, `affected_slides`, `confidence` |

#### literature_hunter

| status | content |
|--------|---------|
| `running` | début de l'hypothèse recherchée (80 chars) |
| `done` | JSON string avec `papers` (list), `similar_cases` (int), `key_findings`, `confidence` |

#### differential_diagnostician

| status | content |
|--------|---------|
| `running` | "Etablissement diagnostics differentiels" |
| `done` | JSON string avec `primary_diagnosis`, `differentials` (list: name/probability/rationale), `confidence` |

#### quality_control

| status | content |
|--------|---------|
| `running` | "Verification qualite et coherence" |
| `done` | JSON string avec `approved` (bool), `challenges` (list), `resolution`, `qc_score` |

#### report_writer

| status | content |
|--------|---------|
| `running` | "Redaction rapport CAP final" |
| `done` | Rapport CAP texte complet (format clinique) |

---

## GET /health

```json
{"ok": true, "version": "0.1.0"}
```

---

## Exemple curl complet

```bash
# 1. Lancer l'analyse
curl -X POST http://localhost:8001/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "case-2026-001",
    "patient_id": "P001",
    "slide_paths": ["data/slides/lame_A.svs", "data/slides/lame_B.svs"],
    "clinical_data": {"age": 62, "sexe": "M", "antecedents": "diabete type 2"}
  }'

# Réponse immédiate :
# {"case_id": "case-2026-001", "status": "started"}

# 2. Ecouter les events WebSocket (nécessite wscat)
wscat -c ws://localhost:8001/ws/case-2026-001

# 3. Health check
curl http://localhost:8001/health
```

### Exemple Python (écoute WebSocket)

```python
import asyncio, json, websockets, aiohttp

async def run_analysis():
    case_id = "case-2026-001"
    uri = f"ws://localhost:8001/ws/{case_id}"

    async with websockets.connect(uri) as ws:
        # Déclencher le pipeline
        async with aiohttp.ClientSession() as session:
            await session.post("http://localhost:8001/api/analyze", json={
                "case_id": case_id,
                "patient_id": "P001",
                "slide_paths": ["data/slides/demo.svs"]
            })

        # Lire les events jusqu'à completion
        async for msg in ws:
            event = json.loads(msg)
            print(f"[{event['agent']}] {event['status']}: {event.get('content','')[:80]}")
            if event.get("agent") == "pipeline" and event.get("status") == "complete":
                break

asyncio.run(run_analysis())
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MOCK_MODE` | `false` | `true` = bypass LLM, réponses hardcodées réalistes (cancer pancréas) |
| `ANTHROPIC_API_KEY` | `dummy` | Clé API Anthropic (requis si MOCK_MODE=false) |
| `LLM_BASE_URL` | `https://api.anthropic.com/v1` | Base URL OpenAI-compatible |
| `LLM_MODEL` | `claude-sonnet-4-6` | Modèle utilisé |

Lancement en mode mock :
```bash
MOCK_MODE=true python3 -m uvicorn backend.main:app --port 8001
```
