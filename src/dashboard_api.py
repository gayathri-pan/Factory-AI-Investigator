"""Firebase-authenticated dashboard API: fleet history and verified live demo."""
import logging
import json
import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import auth
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.cloud import bigquery, firestore, run_v2, tasks_v2
from google.api_core.exceptions import AlreadyExists
from google.protobuf import duration_pb2

PROJECT = 'project-e64210d0-f317-4050-833'
DATASET = f'{PROJECT}.factory_ai_investigator'
ALLOWED_UID = os.environ['DASHBOARD_UID']
firebase_admin.initialize_app(options={'projectId': PROJECT})
db = firestore.Client(project=PROJECT)
bq = bigquery.Client(project=PROJECT, location='asia-south1')
jobs = run_v2.JobsClient()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[f'https://{PROJECT}.web.app', f'https://{PROJECT}.firebaseapp.com'], allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])
SENSORS = ('temperature', 'vibration', 'pressure', 'rpm', 'power_consumption')
MACHINES = tuple(f'M-{n}' for n in range(101, 106))


def authorized(authorization: str = Header(default='')):
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(401, 'Sign in required.')
    try:
        claims = auth.verify_id_token(token)
    except (ValueError, auth.InvalidIdTokenError):
        raise HTTPException(401, 'Sign-in expired. Please sign in again.')
    if claims.get('firebase', {}).get('sign_in_provider') != 'google.com':
        raise HTTPException(403, 'Please sign in with Google.')
    return claims['uid']


def query(sql, params=()):
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter(*p) for p in params])
    return [dict(r.items()) for r in bq.query(sql, job_config=config, location='asia-south1').result()]


def check_machine(machine_id):
    if machine_id not in MACHINES:
        raise HTTPException(400, 'Choose a machine from M-101 through M-105.')


def get_event(event_id):
    if not re.fullmatch(r'evt_[0-9a-f]{64}', event_id):
        raise HTTPException(400, 'Invalid historical event ID.')
    rows = query(f'SELECT * FROM `{DATASET}.anomaly_events` WHERE event_id=@id LIMIT 2', [('id','STRING',event_id)])
    if not rows:
        raise HTTPException(404, 'Event not found.')
    if len(rows) != 1:
        raise HTTPException(409, 'Duplicate event ID.')
    return rows[0]


@firestore.transactional
def reserve_start(transaction, ref):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    now = datetime.now(timezone.utc)
    if data.get('next_allowed_at', now) > now:
        return False
    transaction.set(ref, {'next_allowed_at': now + timedelta(seconds=180), 'requested_at': firestore.SERVER_TIMESTAMP})
    return True


@app.get('/health')
def health():
    return {'status': 'ready', 'version': 'historical-v4'}


@app.post('/api/replay/start', status_code=202)
def start_replay(uid=Depends(authorized)):
    if not reserve_start(db.transaction(), db.collection('dashboard_controls').document('replay')):
        raise HTTPException(429, 'Please wait three minutes between demo starts.')
    try:
        operation = jobs.run_job(request={'name': f'projects/{PROJECT}/locations/asia-south1/jobs/factory-live-replay'}, retry=None, timeout=30)
    except Exception:
        logging.exception('Replay start failed or outcome unknown.')
        raise HTTPException(503, 'Start outcome unknown. Check the latest session before retrying.')
    return {'status': 'starting', 'operation': operation.operation.name, 'machine_id': 'M-103'}


@app.get('/api/machines')
def machines(uid=Depends(authorized)):
    metadata = query(f'SELECT * FROM `{DATASET}.factory_machines` ORDER BY machine_id')
    counts = query(f'''SELECT machine_id, COUNT(*) AS event_count,
        SUM(flagged_window_count) AS flagged_windows,
        MAX(end_time) AS latest_event_end FROM `{DATASET}.anomaly_events` GROUP BY machine_id''')
    by_id = {r['machine_id']:r for r in counts}
    return {'machines': [{**m, **by_id.get(m['machine_id'], {'event_count':0,'flagged_windows':0}), 'live_available':m['machine_id']=='M-103'} for m in metadata if m['machine_id'] in MACHINES]}


@app.get('/api/machines/{machine_id}/records')
def records(machine_id: str, uid=Depends(authorized)):
    check_machine(machine_id)
    p = [('machine','STRING',machine_id)]
    return {
        'maintenance_history':query(f'SELECT * FROM `{DATASET}.maintenance_history` WHERE machine_id=@machine ORDER BY date DESC, maintenance_id LIMIT 101',p),
        'historical_incidents':query(f'SELECT * FROM `{DATASET}.historical_incidents` WHERE machine_id=@machine ORDER BY date DESC, incident_id LIMIT 101',p),
        'scope':'Machine archive, up to 101 records of each type. These records are not necessarily available at a selected historical event.'}


@app.get('/api/events')
def events(machine_id: str = Query(...), uid=Depends(authorized)):
    check_machine(machine_id)
    rows = query(f'SELECT * FROM `{DATASET}.anomaly_events` WHERE machine_id=@machine ORDER BY start_time DESC, event_id LIMIT 101', [('machine','STRING',machine_id)])
    return {'events':rows[:100], 'truncated':len(rows)>100}


@app.get('/api/events/{event_id}/context')
def context(event_id: str, uid=Depends(authorized)):
    event = get_event(event_id)
    machine, start, end = event['machine_id'],event['start_time'],event['end_time']
    if start is None or end is None or end < start:
        raise HTTPException(409, 'Invalid event boundaries.')
    wp = [('machine','STRING',machine),('start','TIMESTAMP',start),('end','TIMESTAMP',end)]
    hp = [('machine','STRING',machine),('day','DATE',start.date())]
    aggregates = ','.join(f'MIN({s}) AS min_{s}, MAX({s}) AS max_{s}, AVG({s}) AS mean_{s}, COUNT({s}) AS valid_{s}_count' for s in SENSORS)
    summary = query(f'''SELECT COUNT(*) AS sensor_readings_found, COUNT(DISTINCT timestamp) AS distinct_sensor_timestamps,
        MIN(timestamp) AS first_sensor_timestamp, MAX(timestamp) AS last_sensor_timestamp, {aggregates}
        FROM `{DATASET}.sensors` WHERE machine_id=@machine AND timestamp BETWEEN @start AND @end''',wp)[0]
    readings = query(f'''SELECT timestamp, machine_id, {','.join(SENSORS)} FROM `{DATASET}.sensors`
        WHERE machine_id=@machine AND timestamp BETWEEN @start AND @end ORDER BY timestamp LIMIT 2001''',wp)
    logs = query(f'''SELECT * FROM `{DATASET}.machine_logs` WHERE machine_id=@machine
        AND timestamp BETWEEN @start AND @end ORDER BY timestamp, component, message LIMIT 201''',wp)
    maintenance = query(f'SELECT * FROM `{DATASET}.maintenance_history` WHERE machine_id=@machine AND date<@day ORDER BY date DESC, maintenance_id LIMIT 21',hp)
    incidents = query(f'SELECT * FROM `{DATASET}.historical_incidents` WHERE machine_id=@machine AND date<@day ORDER BY date DESC, incident_id LIMIT 21',hp)
    return {'anomaly_event':event, 'sensor_summary':summary, 'readings':readings[:2000], 'readings_truncated':len(readings)>2000,
        'machine_logs':logs[:200], 'logs_truncated':len(logs)>200, 'maintenance_history':maintenance[:20],
        'historical_incidents':incidents[:20], 'history_truncated':len(maintenance)>20 or len(incidents)>20,
        'investigation_cutoff':end, 'history_exclusive_date':start.date(),
        'note':'Synthetic historical review. Summary statistics are not trends. Units and limits are unestablished. History uses earlier dates; record creation times are unavailable.'}


@app.get('/api/events/{event_id}/reports')
def event_reports(event_id: str, uid=Depends(authorized)):
    get_event(event_id)
    return {'reports':query(f'''SELECT investigation_id, created_at, status, model_name, prompt_version
        FROM `{DATASET}.investigation_reports` WHERE event_id=@event AND status='completed'
        ORDER BY created_at DESC LIMIT 10''',[('event','STRING',event_id)])}


@app.get('/api/reports/{investigation_id}')
def report(investigation_id: str, uid=Depends(authorized)):
    if not re.fullmatch(r'inv_[0-9a-f]{32,64}',investigation_id):
        raise HTTPException(400,'Invalid report ID.')
    rows = query(f'''SELECT investigation_id, event_id, machine_id, created_at, status, report_markdown,
        TO_JSON_STRING(investigation_context) AS context_json FROM `{DATASET}.investigation_reports`
        WHERE investigation_id=@id LIMIT 2''',[('id','STRING',investigation_id)])
    if not rows:
        raise HTTPException(404,'No saved report found.')
    if len(rows)!=1:
        raise HTTPException(409,'Duplicate report ID.')
    return rows[0]


class EngineerReview(BaseModel):
    status: str = Field(pattern=r"^(reviewed|needs_follow_up)$")
    note: str = Field(default="", max_length=2000)


def review_ref(investigation_id, uid):
    if not re.fullmatch(r"inv_[0-9a-f]{32,64}", investigation_id):
        raise HTTPException(400, "Invalid report ID.")
    key = hashlib.sha256(f"{investigation_id}|{uid}".encode()).hexdigest()
    return db.collection("investigation_reviews").document(key)


def shared_review(data, uid):
    reviewer = data.get("reviewer_uid")
    known = isinstance(reviewer, str) and bool(reviewer.strip())

    return {
        "reviewer_label": (
            "Reviewer " + hashlib.sha256(reviewer.encode()).hexdigest()[:10]
            if known else "Unattributed review"
        ),
        "is_yours": known and reviewer == uid,
        "status": data.get("status"),
        "note": data.get("note") or "",
        "updated_at": data.get("updated_at"),
    }


@app.get("/api/reports/{investigation_id}/review")
def get_review(investigation_id: str, uid=Depends(authorized)):
    report(investigation_id, uid)
    snapshot = review_ref(investigation_id, uid).get(timeout=30)
    from google.cloud.firestore_v1.base_query import FieldFilter
    snapshots = list(db.collection("investigation_reviews").where(
        filter=FieldFilter("investigation_id", "==", investigation_id)
    ).limit(101).stream(timeout=30))
    reviews = [shared_review(item.to_dict(), uid) for item in snapshots[:100]]
    reviews.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {
        "review": shared_review(snapshot.to_dict(), uid) if snapshot.exists else None,
        "reviews": reviews,
        "truncated": len(snapshots) > 100,
    }


@app.post("/api/reports/{investigation_id}/review")
def save_review(investigation_id: str, review: EngineerReview, uid=Depends(authorized)):
    report(investigation_id, uid)
    note = review.note.strip()
    if not note:
        raise HTTPException(400, "Add a short review note before saving.")
    ref = review_ref(investigation_id, uid)
    ref.set({
        "investigation_id": investigation_id,
        "reviewer_uid": uid,
        "status": review.status,
        "note": note,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, timeout=30)
    saved = ref.get(timeout=30)
    if not saved.exists:
        raise HTTPException(503, "Review could not be verified. Refresh before retrying.")
    return {"status": "saved", "review": shared_review(saved.to_dict(), uid)}


HISTORICAL_COLLECTION = 'historical_investigations'
WORKER_URL = os.getenv('INVESTIGATION_WORKER_URL', 'https://factory-investigation-worker-231017395374.asia-south1.run.app').rstrip('/')
TASK_INVOKER = f'factory-task-invoker@{PROJECT}.iam.gserviceaccount.com'


class HistoricalStart(BaseModel):
    retry: bool = False


def history_public(data):
    fields = ('event_id', 'machine_id', 'investigation_status', 'investigation_stage',
        'investigation_id', 'investigation_reason', 'investigation_missing_information',
        'investigation_updated_at', 'investigation_finished_at', 'dispatch_status',
        'dispatch_generation', 'evidence_collected', 'accepted_evidence',
        'evidence_gate', 'investigation_query')
    return {k: data[k] for k in fields if k in data}


def latest_saved_history(event):
    candidates = query(f'''SELECT investigation_id, event_id, machine_id,
        source_run_id, status, TO_JSON_STRING(investigation_context) AS context_json
        FROM `{DATASET}.investigation_reports`
        WHERE event_id=@id AND status='completed'
        ORDER BY created_at DESC LIMIT 10''', [('id', 'STRING', event['event_id'])])
    for saved in candidates:
        try:
            context = json.loads(saved['context_json']) or {}
            cutoff = datetime.fromisoformat(context['investigation_cutoff'].replace('Z', '+00:00'))
        except (KeyError, ValueError, TypeError):
            continue
        if (saved.get('machine_id') == event['machine_id']
            and saved.get('source_run_id') == event['source_run_id']
            and cutoff == event['end_time']):
            return saved
    return None


@firestore.transactional
def prepare_historical(transaction, ref, control, event, uid, retry):
    snapshot = ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    status = data.get('investigation_status')
    if status == 'report_ready':
        return data, False
    if status == 'investigating':
        return data, False
    if status == 'needs_review':
        return data, False
    if status in ('failed', 'blocked') and not retry:
        return data, False
    if status == 'queued':
        # Retry the same task submission, including an uncertain response.
        return data, True

    limit = control.get(transaction=transaction).to_dict() or {}
    now = datetime.now(timezone.utc)
    if limit.get('next_allowed_at', now) > now:
        raise HTTPException(429, 'Please wait 30 seconds between new historical investigations.')
    generation = int(data.get('dispatch_generation', 0)) + 1
    changes = {
        'event_id': event['event_id'], 'machine_id': event['machine_id'],
        'source_run_id': event['source_run_id'], 'requested_by': uid,
        'investigation_status': 'queued', 'investigation_stage': 'queued',
        'dispatch_generation': generation, 'dispatch_status': 'pending',
        'investigation_reason': '', 'investigation_missing_information': [],
        'investigation_error_type': None, 'evidence_collected': False,
        'accepted_evidence': [], 'evidence_gate': {}, 'investigation_query': '',
        'investigation_updated_at': firestore.SERVER_TIMESTAMP,
    }
    if not snapshot.exists:
        changes['created_at'] = firestore.SERVER_TIMESTAMP
    transaction.set(ref, changes, merge=True)
    transaction.set(control, {'next_allowed_at': now + timedelta(seconds=30)})
    return {**data, **changes}, True


def enqueue_historical(event_id, generation):
    client = tasks_v2.CloudTasksClient()
    try:
        task_id = 'history-' + hashlib.sha256(f'{event_id}|{generation}'.encode()).hexdigest()
        parent = client.queue_path(PROJECT, 'asia-south1', 'factory-investigations')
        name = client.task_path(PROJECT, 'asia-south1', 'factory-investigations', task_id)
        task = tasks_v2.Task(
            name=name,
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=WORKER_URL + '/tasks/investigate-historical',
                headers={'Content-Type':'application/json'},
                body=json.dumps({'event_id':event_id, 'dispatch_generation':generation}).encode(),
                oidc_token=tasks_v2.OidcToken(service_account_email=TASK_INVOKER, audience=WORKER_URL),
            ),
            dispatch_deadline=duration_pb2.Duration(seconds=960),
        )
        try:
            client.create_task(request={'parent':parent, 'task':task}, timeout=30)
            outcome = 'submitted'
        except AlreadyExists:
            outcome = 'already_exists'
        return name, outcome
    finally:
        client.transport.close()


@app.post('/api/events/{event_id}/investigate', status_code=202)
def start_historical(event_id: str, body: HistoricalStart, uid=Depends(authorized)):
    event = get_event(event_id)
    saved = latest_saved_history(event)
    if saved:
        return {'event_id':event_id, 'machine_id':event['machine_id'],
            'investigation_status':'report_ready', 'investigation_stage':'completed',
            'investigation_id':saved['investigation_id'], 'reused':True}
    ref = db.collection(HISTORICAL_COLLECTION).document(event_id)
    data, enqueue = prepare_historical(db.transaction(), ref,
        db.collection('dashboard_controls').document('historical'), event, uid, body.retry)
    if not enqueue:
        return history_public(data)
    generation = int(data['dispatch_generation'])
    try:
        task_name, outcome = enqueue_historical(event_id, generation)
    except Exception as exc:
        logging.exception('Historical task submission failed or outcome unknown.')
        try:
            ref.update({'dispatch_status':'submission_error',
                'dispatch_error_type':type(exc).__name__}, timeout=30)
        except Exception:
            logging.exception('Could not record submission failure.')
        raise HTTPException(503, 'Task submission outcome is unknown. Check status before retrying.')
    # Worker may already be running: never reset its investigation status.
    ref.update({'dispatch_status':outcome, 'task_name':task_name}, timeout=30)
    return history_public(ref.get(timeout=30).to_dict() or {})


@app.get('/api/events/{event_id}/investigation')
def historical_status(event_id: str, uid=Depends(authorized)):
    if not re.fullmatch(r'evt_[0-9a-f]{64}', event_id):
        raise HTTPException(400, 'Invalid event ID.')
    snapshot = db.collection(HISTORICAL_COLLECTION).document(event_id).get(timeout=30)
    if snapshot.exists:
        return history_public(snapshot.to_dict() or {})
    get_event(event_id)
    return {'event_id':event_id, 'investigation_status':'not_requested',
        'investigation_stage':'not_started', 'evidence_collected':False}
