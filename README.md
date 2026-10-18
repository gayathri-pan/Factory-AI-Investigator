# Factory AI Investigator

A cloud prototype that helps maintenance engineers investigate machine anomaly alerts using sensor observations, operational records, and relevant technical documentation.

**Prototype:** https://project-e64210d0-f317-4050-833.web.app/

Sign in with Google to explore the dashboard.

> This project uses synthetic factory data and demonstration manuals. Model detections are not confirmed equipment failures. Generated reports support human review and do not authorize maintenance actions.

## Problem

An anomaly alert identifies a suspicious sensor window, but engineers still need to determine what happened and what to investigate next.

Relevant evidence is scattered across sensor readings, machine logs, maintenance records, historical incidents, and technical manuals. Factory AI Investigator brings this information together in an investigation report with supporting references and explicit evidence gaps.

## Features

- Historical event exploration for five machines, M-101 through M-105.
- Recorded sensor charts and event-window summaries.
- Scoped machine logs and earlier maintenance and incident records.
- On-demand investigation of a selected historical event.
- Accelerated live simulation for the M-103 conveyor.
- Automatic investigation after the first replay alert.
- Machine-aware retrieval of technical manual passages.
- Evidence assessment before report generation.
- Saved reports with manual references and missing-information explanations.
- Shared review notes with Reviewed and Needs follow-up dispositions.

Google sign-in identifies contributors. It does not verify their professional qualifications.

## How It Works

### Detection

The final XGBoost classifier uses 96 engineered features from five sensor signals:

- Temperature
- Vibration
- Pressure
- RPM
- Power consumption

Each window contains 30 one-minute readings. Scoring advances in five-minute steps.

The validation-selected detection threshold is:

`0.25487801432609558`

Consecutive flagged windows with start times five minutes apart form a detection event. Events are grouped separately by machine, model version, inference run, and dataset partition.

### Investigation

1. Select a historical event or detect the first alert during replay.
2. Build event-specific context from sensor observations and operational records.
3. Retrieve relevant machine-specific and general manual passages.
4. Assess evidence relevance and sufficiency.
5. Generate an investigation report using Gemini on Vertex AI.
6. Validate report structure and evidence references.
7. Store the report in BigQuery and verify it by reading it back.
8. Update investigation status in Firestore.
9. Let users inspect the evidence and save review notes.

Structural validation does not independently establish factual correctness or root cause.

### Investigation Scope

For live replay, the initial investigation uses a frozen first-alert snapshot. Later readings and event updates are excluded from that initial report.

For historical investigation, the context covers the complete selected grouped event.

Maintenance and incident context includes earlier calendar dates. The source records lack recorded-at timestamps, so historical availability cannot be fully established.

## Google Cloud Architecture

| Service | Purpose |
|---|---|
| Firebase Hosting | Dashboard hosting |
| Firebase Authentication | Google sign-in |
| Cloud Run | Dashboard API and private investigation worker |
| Cloud Run Jobs | Batch inference and sensor replay |
| Cloud Tasks | Authenticated asynchronous investigation requests |
| BigQuery | Operational datasets, predictions, events, and reports |
| Firestore | Replay observations, progress, event state, and reviews |
| Cloud Storage | Model files and versioned retrieval artifacts |
| Vertex AI | Gemini evidence assessment and report generation |
| Cloud Build | Container builds |
| Artifact Registry | Container image storage |
| Cloud Logging | Application and execution logs |

Python orchestrates context construction, retrieval, evidence assessment, generation, validation, and storage.

The replay continues independently while the investigation worker processes the alert.

## Retrieval

- Embedding model: `BAAI/bge-small-en-v1.5`
- Embedding dimension: 384
- Similarity: cosine
- Vector store: Qdrant
- Exported knowledge base: 162 manual chunks
- Default chunk size: 500 characters
- Chunk overlap: 100 characters
- Default retrieved evidence: up to three passages

The cloud worker downloads versioned artifacts and restores Qdrant in memory. It does not use a persistent managed Qdrant server.

Retrieval filters restrict evidence to the requested machine and eligible general documentation.

## Dataset

The synthetic V3 dataset is under:

`data/yearly_experiment_v3/raw/`

| File | Contents |
|---|---|
| `factory_machines.csv` | Machine metadata |
| `sensors.csv.gz` | Compressed sensor observations |
| `machine_logs.csv` | Machine logs |
| `maintenance_history.csv` | Maintenance records |
| `historical_incidents.csv` | Historical incident records |
| `scenario_labels.csv` | Synthetic scenario annotations for training and evaluation |

Scenario annotations are not inputs to replay prediction or the investigation query.

Extract the sensor file before running scripts that expect `sensors.csv`:

```bash
python -c "import gzip,shutil; from pathlib import Path; p=Path('data/yearly_experiment_v3/raw/sensors.csv.gz'); f=gzip.open(p,'rb'); o=p.with_suffix('').open('wb'); shutil.copyfileobj(f,o); f.close(); o.close()"
```

The replay input is:

`data/replay/m103_demo_v1.csv`

It contains raw observations without scenario labels or expected predictions.

Synthetic manuals are under `data/manuals/`. They are demonstration documents, not verified OEM instructions.

## Model and Evaluation

Final model artifacts are under:

`models/xgboost_experiment_30m_v3_dataset/`

- `xgboost_binary_v3_dataset.json`
- `feature_columns_v3_dataset.json`
- `validation_threshold_v3_dataset.json`

Evaluation files are under:

`data/xgboost_experiment_30m_v3_dataset/results/`

They include test and validation metrics, scenario detection results, and overall feature importance.

Overall feature importance does not explain the contribution of features to an individual event.

### Batch Processing Results

| Machine | Scored windows | Flagged windows | Grouped events |
|---|---:|---:|---:|
| M-101 | 105,105 | 637 | 99 |
| M-102 | 105,105 | 630 | 97 |
| M-103 | 105,105 | 714 | 95 |
| M-104 | 105,105 | 732 | 99 |
| M-105 | 105,105 | 782 | 94 |
| **Total** | **525,525** | **3,495** | **484** |

These totals cover all scored dataset partitions. They are processing volumes, not held-out accuracy results or counts of confirmed failures.

### Replay Feature Parity

Ten sampled held-out windows across the five machines were checked against features recomputed from raw observations.

- Features matched within numerical tolerance.
- Model probabilities and threshold decisions matched.
- Largest observed feature difference was approximately `5.6e-11`.

This sampled check verifies consistency between the two feature paths. It is not an exhaustive correctness or model accuracy claim.

## Live Demonstration

The configured M-103 scenario uses 100 prerecorded synthetic readings.

- First 30 readings preload the rolling window.
- Remaining 70 readings arrive at a target rate of one simulated minute per second.
- The model scores 15 windows.
- Eight consecutive flagged windows form one event.
- The first alert automatically queues an investigation.

The demonstration uses actual feature computation and model inference. It does not display preassigned predictions.

A later unflagged window ends the flagged sequence; it does not establish physical recovery.

## Repository Structure

```text
src/
  anomaly_detection/   Final preprocessing, training, evaluation, batch inference
  investigation/       Context, evidence gate, reports, worker, report storage
  rag/                 Manual loading, embeddings, vector store, retrieval
  dashboard_api.py     Authenticated dashboard backend

scripts/               Replay, artifact export, and validation utilities
public/                Dashboard assets
models/                Final XGBoost artifacts
data/manuals/          Synthetic technical documentation
data/replay/           Small replay dataset
data/yearly_experiment_v3/raw/
                       Synthetic source dataset
```

## Local Setup

Requirements:

- Python 3.12
- uv
- Google Cloud CLI for authenticated cloud operations
- Firebase CLI for Hosting deployment

Install project dependencies:

```bash
uv sync
```

For PowerShell, expose the source packages:

```powershell
$env:PYTHONPATH = "$PWD\src"
```

For Bash:

```bash
export PYTHONPATH="$PWD/src"
```

Authenticate local application credentials when using cloud-backed modules:

```bash
gcloud auth application-default login
```

Example environment configuration:

```dotenv
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=asia-south1
BIGQUERY_LOCATION=asia-south1
GOOGLE_GENAI_USE_VERTEXAI=true
LLM_MODEL=gemini-3.5-flash
DASHBOARD_UID=YOUR_OWNER_FIREBASE_UID
```

Additional replay, Cloud Tasks, and artifact settings depend on the relevant script configuration.

Never commit `.env`, service-account keys, access tokens, or application credentials.

## Validation Commands

Check replay feature parity:

```bash
uv run python scripts/check_replay_feature_parity.py
```

Inspect the local replay:

```bash
uv run python scripts/inspect_replay_segment.py
```

Run cloud-backed historical investigation:

```bash
uv run python -m investigation.cloud_investigator --event-id YOUR_EVENT_ID
```

Cloud-backed commands require provisioned resources, matching artifacts, and appropriate IAM permissions. They may incur charges.

## Deployment

The repository includes separate Dockerfiles and build configurations for:

- Batch inference
- Replay execution
- Investigation worker
- Dashboard API

Deployment requires configuring the project, bucket, BigQuery tables, Firestore database, Firebase Authentication, Cloud Tasks queue, and service-account permissions.

Existing deployment files contain project-specific values. Review and replace these before deploying into another project.

The investigation worker remains private. Cloud Tasks invokes it using an authenticated service account.

Browser clients read permitted replay data and use the authenticated dashboard API for application actions.

## Limitations

- Evaluation uses synthetic data.
- Live simulation currently supports M-103 only.
- Sensor units, equipment mappings, and operating limits are not established.
- Historical incidents suggest possible explanations rather than proving the current cause.
- Report validation checks structure and references, not factual correctness.
- Retries can repeat generation work before a report is stored.
- Shared reviews are editable feedback, not an immutable audit trail.
- Real-factory accuracy, investigation time savings, and downtime reduction have not been measured.

## Author

Gayathri Mahesh

Built for the AI Builder Cup.
