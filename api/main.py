"""
FastAPI application — ResearchLens API
--------------------------------------
Routes:
  POST /api/research      → enqueue pipeline job, returns job_id
  GET  /api/status/{id}   → poll job status + result
  GET  /api/jobs          → list all jobs (debugging)
  GET  /health            → liveness check

Job persistence:
  Each job is written to data/jobs/{job_id}.json on every update.
  On server startup, all existing job files are loaded back into memory.
  Jobs older than JOB_TTL_HOURS (default 1h) are cleaned up automatically.
"""

try:
    from rank_bm25 import BM25Okapi  # noqa: F401 — verify venv is active
except ImportError:
    import sys
    print(
        "\n❌  Missing dependencies — virtual environment not active.\n"
        "    Run:  .venv\\scripts\\activate\n"
        "    Then: python -m api.main\n",
        file=sys.stderr,
    )
    sys.exit(1)

import uuid
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.schemas import ResearchRequest, JobStatus, NoveltyRequest, NoveltyResponse, LitReviewResponse, AuthRequest, AuthResponse
from pipeline._llm import generate_text, generate_json
from pipeline.embedding import _embed_batch
import numpy as np
from api import auth
from fastapi import Header

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JOBS_DIR = Path("data/jobs")          # one JSON file per job
JOB_TTL_HOURS = 168                   # delete jobs older than 1 week (for dashboard)
CLEANUP_INTERVAL_SECONDS = 600        # run cleanup every 10 minutes

# In-memory job store — seeded from disk on startup
_jobs: dict[str, dict[str, Any]] = {}

# Per-job WebSocket event queues — frontend subscribes to receive real-time progress
_ws_queues: dict[str, list[asyncio.Queue]] = {}


# ---------------------------------------------------------------------------
# Disk persistence helpers
# ---------------------------------------------------------------------------

def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _save_job(job_id: str) -> None:
    """Write a single job to disk (non-blocking write, called after every update)."""
    try:
        job = _jobs.get(job_id)
        if job is None:
            return
        _job_path(job_id).write_text(
            json.dumps(job, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"Could not persist job {job_id} to disk: {e}")


def _load_jobs_from_disk() -> None:
    """
    On startup, reload all job JSON files from data/jobs/.
    Jobs that are still 'running' (server crashed mid-run) are marked 'error'.
    """
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    loaded = 0
    for f in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(f.read_text(encoding="utf-8"))
            job_id = job.get("job_id")
            if not job_id:
                continue
            # If server crashed while this job was running, mark it failed
            if job.get("status") in ("running", "queued"):
                job["status"] = "error"
                job["error"] = "Server restarted while job was running."
                job["current_step"] = "Error"
                f.write_text(json.dumps(job, ensure_ascii=False, default=str), encoding="utf-8")
            _jobs[job_id] = job
            loaded += 1
        except Exception as e:
            logger.warning(f"Could not load job file {f.name}: {e}")
    if loaded:
        logger.info(f"Loaded {loaded} jobs from disk.")


def _delete_job(job_id: str) -> None:
    """Remove a job from memory and disk."""
    _jobs.pop(job_id, None)
    path = _job_path(job_id)
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.warning(f"Could not delete job file {job_id}: {e}")


# ---------------------------------------------------------------------------
# TTL cleanup
# ---------------------------------------------------------------------------

async def _cleanup_loop() -> None:
    """
    Background coroutine: every CLEANUP_INTERVAL_SECONDS, delete jobs whose
    'created_at' timestamp is older than JOB_TTL_HOURS.
    Only completed/errored jobs are cleaned up — running jobs are never deleted.
    """
    ttl_seconds = JOB_TTL_HOURS * 3600
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        expired = [
            jid for jid, j in list(_jobs.items())
            if j.get("status") in ("done", "error")
            and (now - j.get("created_at", now)) > ttl_seconds
        ]
        for jid in expired:
            _delete_job(jid)
        if expired:
            logger.info(f"TTL cleanup: removed {len(expired)} expired jobs.")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ResearchLens API starting up …")
    Path("data").mkdir(exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    _load_jobs_from_disk()
    # Start TTL cleanup background task
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()
    logger.info("ResearchLens API shutting down.")


app = FastAPI(
    title="ResearchLens API",
    description="Automated research paper analysis pipeline",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Path("data").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="data"), name="static")


# ---------------------------------------------------------------------------
# Job management helpers
# ---------------------------------------------------------------------------

def _update_job(job_id: str, **kwargs) -> None:
    """Update job fields in memory, persist to disk, and push to WebSocket subscribers."""
    new_log = kwargs.pop("new_log", None)
    if new_log:
        if "logs" not in _jobs[job_id]:
            _jobs[job_id]["logs"] = []
        _jobs[job_id]["logs"].append(new_log)
    _jobs[job_id].update(kwargs)
    _save_job(job_id)
    # Push progress event to all WebSocket subscribers for this job
    event = {
        "status": _jobs[job_id].get("status"),
        "progress": _jobs[job_id].get("progress"),
        "current_step": _jobs[job_id].get("current_step"),
        "logs": _jobs[job_id].get("logs", [])
    }
    if new_log:
        event["new_log"] = new_log
    for q in _ws_queues.get(job_id, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # subscriber is slow, skip this update


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------

async def _run_pipeline_job(job_id: str, request: ResearchRequest) -> None:
    """Async wrapper that runs the blocking pipeline in a thread pool."""
    import concurrent.futures
    import threading
    from pipeline.orchestrator import run_pipeline

    _update_job(job_id, status="running", progress=5, current_step="Starting pipeline …")

    loop = asyncio.get_event_loop()

    class JobLogHandler(logging.Handler):
        def __init__(self, cb, tid):
            super().__init__()
            self.cb = cb
            self.tid = tid
            
        def emit(self, record):
            if threading.get_ident() == self.tid:
                try:
                    self.cb(None, None, self.format(record))
                except Exception:
                    pass

    def _sync_run():
        def _cb(step: str, pct: int, log_msg: str = None):
            def _threadsafe_update():
                update_data = {}
                if step is not None: update_data["current_step"] = step
                if pct is not None: update_data["progress"] = pct
                if log_msg is not None: update_data["new_log"] = log_msg
                if update_data:
                    _update_job(job_id, **update_data)
            
            # Since we are inside a background thread, pushing to asyncio queue
            # must be scheduled on the event loop to ensure it sends via WebSockets
            if hasattr(loop, "_thread_id") and threading.get_ident() == loop._thread_id:
                _threadsafe_update()
            else:
                loop.call_soon_threadsafe(_threadsafe_update)

        # 1. Capture Python pipeline logging (logger.info, logger.error)
        class PipelineHandler(logging.Handler):
            def emit(self, record):
                if record.name.startswith("pipeline"):
                    try:
                        _cb(None, None, self.format(record))
                    except Exception:
                        pass
                        
        handler = PipelineHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        # Using a specific logger or the root logger
        logging.getLogger().addHandler(handler)

        # 2. Safely capture stdout/stderr (print statements and underlying libraries)
        import sys
        class StdStreamHook:
            def __init__(self, original):
                self.original = original
            def write(self, s):
                self.original.write(s)
                # Ignore empty strings and carriage returns (used by progress bars like tqdm)
                # But allow regular printing!
                clean_s = s.replace("\r", "").strip()
                if clean_s:
                    try: _cb(None, None, clean_s)
                    except Exception: pass
            def flush(self):
                self.original.flush()
                
        old_out = sys.stdout
        old_err = sys.stderr
        sys.stdout = StdStreamHook(old_out)
        sys.stderr = StdStreamHook(old_err)

        try:
            return run_pipeline(
                topic=request.topic,
                max_papers=request.max_papers,
                min_year=request.min_year,
                use_rebel=request.use_rebel,
                use_cache=request.use_cache,
                on_progress=_cb,
            )
        finally:
            logging.getLogger().removeHandler(handler)
            sys.stdout = old_out
            sys.stderr = old_err

    try:
        _update_job(job_id, progress=10, current_step="Retrieving papers …")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = await loop.run_in_executor(pool, _sync_run)

        _update_job(
            job_id,
            status="done",
            progress=100,
            current_step="Complete",
            result=_serialise_result(result),
        )
        logger.info(f"Job {job_id} completed successfully.")
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        _update_job(job_id, status="error", progress=0, current_step="Error", error=str(e))


def _serialise_result(result: dict) -> dict:
    """Recursively convert all numpy types to native Python for JSON serialisation."""
    import numpy as np

    def _convert(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        if isinstance(obj, tuple):
            return [_convert(i) for i in obj]
        return obj

    return _convert(result)


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", response_model=AuthResponse)
async def register(req: AuthRequest):
    if auth.get_user_by_email(req.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = auth.create_user(req.email, req.password)
    token = auth.create_session(user_id)
    return {"token": token, "email": req.email}

@app.post("/api/auth/login", response_model=AuthResponse)
async def login(req: AuthRequest):
    user_id = auth.verify_user(req.email, req.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_session(user_id)
    return {"token": token, "email": req.email}

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "")
    return auth.get_user_from_token(token)

@app.get("/api/user/jobs")
async def list_user_jobs(user_id: int = Depends(get_current_user)):
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_jobs = [
        {
            "job_id": j["job_id"],
            "topic": j.get("topic", "Unknown"),
            "status": j["status"],
            "created_at": j.get("created_at"),
            "progress": j["progress"]
        }
        for j in _jobs.values()
        if j.get("user_id") == user_id
    ]
    return sorted(user_jobs, key=lambda x: x.get("created_at", 0), reverse=True)


# ---------------------------------------------------------------------------
# Pipeline Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "jobs_in_memory": len(_jobs),
        "jobs_on_disk": len(list(JOBS_DIR.glob("*.json"))),
    }


@app.post("/api/research", response_model=JobStatus, status_code=202)
async def start_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    user_id: Optional[int] = Depends(get_current_user)
):
    """
    Enqueue a pipeline job. Returns a job_id immediately.
    Poll GET /api/status/{job_id} for progress and results.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "current_step": "Queued",
        "result": None,
        "error": None,
        "topic": request.topic,
        "user_id": user_id,
        "created_at": time.time(),   # used for TTL cleanup
    }
    _save_job(job_id)   # persist immediately so the job survives a crash even before it starts
    background_tasks.add_task(_run_pipeline_job, job_id, request)
    logger.info(f"Job {job_id} queued for topic: '{request.topic}'")
    return _jobs[job_id]


@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """
    Poll job status. When status='done', result is included.
    Falls back to disk if the job was evicted from memory (e.g. after restart).
    """
    if job_id not in _jobs:
        # Try loading from disk (e.g. after a server restart)
        path = _job_path(job_id)
        if path.exists():
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                _jobs[job_id] = job   # cache back into memory
            except Exception:
                raise HTTPException(status_code=404, detail="Job not found")
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/jobs")
async def list_jobs():
    """List all in-memory jobs with basic metadata (for debugging)."""
    return [
        {
            "job_id": jid,
            "status": j["status"],
            "topic": j.get("topic"),
            "progress": j["progress"],
            "created_at": j.get("created_at"),
        }
        for jid, j in _jobs.items()
    ]


@app.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, user_id: int = Depends(get_current_user)):
    """Manually delete a job from memory and disk."""
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    if _jobs[job_id].get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this job")
    _delete_job(job_id)


# ---------------------------------------------------------------------------
# Advanced Phase 2 Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/generate_lit_review", response_model=LitReviewResponse)
async def generate_lit_review(job_id: str):
    if job_id not in _jobs or _jobs[job_id]["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not finished")
    
    result = _jobs[job_id]["result"]
    clusters = result.get("clusters", {})
    papers = result.get("papers", [])
    
    cluster_lines = []
    for cid, c in clusters.items():
        if c.get("is_noise"):
            continue
        p_titles = [p["title"] for p in papers if p.get("cluster_id") == int(cid)][:3]
        cluster_lines.append(f"- Cluster '{c['label']}': {c['paper_count']} papers. Example works: {', '.join(p_titles)}")
        
    prompt = f"""You are a senior academic researcher writing a literature review.
Topic: {result['topic']}

Research clusters identified in this field:
{chr(10).join(cluster_lines)}

Write a professional, 3-paragraph academic literature review synthesizing this field.
Use proper academic framing (e.g., "Early work established...", "Building on this...", "Recent trends focus on...").
Return exactly 3 paragraphs of plain text. Do not use markdown headers."""

    try:
        review_text = generate_text(prompt)
        return LitReviewResponse(literature_review=review_text.strip())
    except Exception as e:
        logger.error(f"Lit review generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate literature review")


@app.post("/api/check_novelty", response_model=NoveltyResponse)
async def check_novelty(req: NoveltyRequest):
    if req.job_id not in _jobs or _jobs[req.job_id]["status"] != "done":
        raise HTTPException(status_code=404, detail="Job not found or not finished")
    
    from pipeline.embedding import embed_papers
    result = _jobs[req.job_id]["result"]
    papers = result.get("papers", [])
    
    if not papers:
        raise HTTPException(status_code=400, detail="No papers found in job")
    
    try:
        # Load cached embeddings for the papers
        embs = embed_papers(papers, topic=result["topic"], field="combined")
        
        # Embed the user's proposal
        proposal_emb = _embed_batch([req.proposal])[0]
        
        # Compute cosine similarity
        norm_embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
        norm_prop = proposal_emb / np.linalg.norm(proposal_emb)
        sims = np.dot(norm_embs, norm_prop)
        
        # Get top 3 closest
        top_indices = np.argsort(sims)[::-1][:3]
        top_score = float(sims[top_indices[0]])
        
        closest_papers = []
        for idx in top_indices:
            p = papers[idx]
            closest_papers.append({
                "title": p["title"],
                "year": p.get("year"),
                "similarity": float(sims[idx]),
                "abstract": p.get("abstract", "")
            })
            
        # Ask LLM to synthesize
        p_text = "\n".join([f"- {p['title']} ({p['year']}): {p['abstract'][:300]}..." for p in closest_papers])
        prompt = f"""You are a brutal but constructive PhD advisor.
The student proposes the following research idea:
"{req.proposal}"

The 3 most similar existing papers in the corpus are:
{p_text}

Max similarity score is {top_score:.2f} (1.0 is identical).

Determine if the student's idea is truly novel, or if they are reinventing the wheel.
Return ONLY a JSON object with this exact format:
{{"is_novel": true/false, "analysis": "1-2 short paragraphs explaining exactly where their idea overlaps with existing work, and what specific angle they should pivot to in order to remain novel."}}"""

        llm_resp = generate_json(prompt)
        
        return NoveltyResponse(
            is_novel=bool(llm_resp.get("is_novel", True)),
            similarity_score=top_score,
            closest_papers=closest_papers,
            analysis=str(llm_resp.get("analysis", ""))
        )
    except Exception as e:
        logger.error(f"Novelty check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# WebSocket progress streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/progress/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str):
    """
    Real-time progress streaming via WebSocket.
    The client connects and receives JSON events:
      {"status": "running", "progress": 40, "current_step": "Embedding + Clustering ..."}
    Connection closes when the job reaches 'done' or 'error'.
    """
    await websocket.accept()

    # Create a queue for this subscriber
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    if job_id not in _ws_queues:
        _ws_queues[job_id] = []
    _ws_queues[job_id].append(queue)

    try:
        # Send current state immediately
        if job_id in _jobs:
            job = _jobs[job_id]
            await websocket.send_json({
                "status": job.get("status"),
                "progress": job.get("progress"),
                "current_step": job.get("current_step"),
                "logs": job.get("logs", []),
            })
            # If already done, send result and close
            if job.get("status") in ("done", "error"):
                await websocket.close()
                return

        # Stream events as they arrive
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=120)
            await websocket.send_json(event)
            if event.get("status") in ("done", "error"):
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        # Unsubscribe
        if job_id in _ws_queues:
            _ws_queues[job_id] = [q for q in _ws_queues[job_id] if q is not queue]
            if not _ws_queues[job_id]:
                del _ws_queues[job_id]


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
