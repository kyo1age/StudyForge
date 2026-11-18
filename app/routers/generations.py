import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..db import read
from ..schemas import GenerateIn, GenerationOut, JobOut, JobStatusOut
from ..security import ensure_client
from ..services import jobs

router = APIRouter(prefix="/api", tags=["generations"])


@router.post("/generations", response_model=JobOut, status_code=201)
def start_generation(body: GenerateIn, background: BackgroundTasks, client_id: str = Depends(ensure_client)):
    key = (client_id, body.document_id, body.page_from, body.page_to, body.material_type)
    job_id, existing, created = jobs.enqueue(key)
    if existing:
        return JobOut(job_id="", status="existing", generation=_to_out(existing))
    if created:
        background.add_task(jobs.run_job, job_id)
    return JobOut(job_id=job_id, status="accepted")


@router.get("/jobs/{job_id}", response_model=JobStatusOut, response_model_exclude_unset=True)
def get_job(job_id: str, client_id: str = Depends(ensure_client)):
    with read() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=? AND client_id=?", (job_id, client_id)).fetchone()
        if not job:
            raise HTTPException(404, "Job not found")
        out = JobStatusOut(job_id=job["id"], status=job["status"], error=job["error"])
        if job["error_status"] is not None:
            out.error_status = job["error_status"]
        if job["status"] == "done":
            generation = conn.execute(
                "SELECT * FROM generations WHERE id=? AND client_id=?",
                (job["generation_id"], client_id),
            ).fetchone()
            out.generation = _to_out(generation) if generation else None
    return out


@router.get("/generations", response_model=list[GenerationOut])
def list_generations(document_id: int | None = None, client_id: str = Depends(ensure_client)):
    query = "SELECT * FROM generations WHERE client_id=?"
    params = [client_id]
    if document_id is not None:
        query += " AND document_id=?"
        params.append(document_id)
    with read() as conn:
        return [_to_out(row) for row in conn.execute(query + " ORDER BY id DESC", params)]


@router.get("/generations/{gen_id}", response_model=GenerationOut)
def get_generation(gen_id: int, client_id: str = Depends(ensure_client)):
    with read() as conn:
        row = conn.execute("SELECT * FROM generations WHERE id=? AND client_id=?", (gen_id, client_id)).fetchone()
    if not row:
        raise HTTPException(404, "Generation not found")
    return _to_out(row)


def _to_out(row) -> GenerationOut:
    return GenerationOut(**{**dict(row), "result": json.loads(row["result"])})

