"""
FastAPI application — ResearchLens API
--------------------------------------
Routes:
  POST /api/research      → enqueue pipeline job, returns job_id
  GET  /api/status/{id}   → poll job status + result
  GET  /api/papers/{topic} → return cached papers for a topic
  GET  /health            → liveness check
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
import logging
import asyncio
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.schemas import ResearchRequest, JobStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# In-memory job store (replace with Redis/Supabase for production)
_jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ResearchLens API starting up …")
    Path("data").mkdir(exist_ok=True)
    yield
    logger.info("ResearchLens API shutting down.")


app = FastAPI(
    title="ResearchLens API",
    description="Automated research paper analysis pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve knowledge graph HTML
Path("data").mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="data"), name="static")


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------

def _update_job(job_id: str, **kwargs):
    _jobs[job_id].update(kwargs)


async def _run_pipeline_job(job_id: str, request: ResearchRequest):
    """Async wrapper that runs the pipeline in a thread pool."""
    import concurrent.futures
    from pipeline.orchestrator import run_pipeline

    _update_job(job_id, status="running", progress=5, current_step="Starting pipeline …")

    loop = asyncio.get_event_loop()

    def _sync_run():
        def _cb(step: str, pct: int):
            _update_job(job_id, current_step=step, progress=pct)

        return run_pipeline(
            topic=request.topic,
            max_papers=request.max_papers,
            min_year=request.min_year,
            use_rebel=request.use_rebel,
            use_cache=request.use_cache,
            on_progress=_cb,
        )

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
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "jobs_in_memory": len(_jobs)}


@app.post("/api/research", response_model=JobStatus, status_code=202)
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
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
    }
    background_tasks.add_task(_run_pipeline_job, job_id, request)
    logger.info(f"Job {job_id} queued for topic: '{request.topic}'")
    return _jobs[job_id]


@app.get("/api/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Poll job status. When status='done', result is included."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/graph/{job_id}")
async def get_graph_html(job_id: str):
    """Return the interactive knowledge graph HTML for a completed job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    if job["status"] != "done":
        raise HTTPException(status_code=202, detail="Job not complete yet")
    html_path = Path("data/knowledge_graph.html")
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Graph not generated")
    return FileResponse(str(html_path), media_type="text/html")


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs (for debugging)."""
    return [
        {"job_id": jid, "status": j["status"], "topic": j.get("topic"), "progress": j["progress"]}
        for jid, j in _jobs.items()
    ]


# ---------------------------------------------------------------------------
# Run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
