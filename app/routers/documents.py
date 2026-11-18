from threading import Lock
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from ..db import read, write
from ..schemas import DocumentDetailOut, DocumentOut, PagePreview
from ..security import ensure_client
from ..services import pdf_service, storage

router=APIRouter(prefix="/api/documents",tags=["documents"])
_progress = {}
_progress_lock = Lock()


@router.get("/upload-progress/{upload_id}")
def upload_progress(upload_id: UUID, client_id: str = Depends(ensure_client)):
    with _progress_lock:
        return _progress.get((client_id, upload_id), {"stage": "waiting"})

@router.post("",response_model=DocumentDetailOut,status_code=201)
async def upload_document(file: UploadFile, client_id: str = Depends(ensure_client),
                          x_upload_id: UUID | None = Header(None)):
    try:
        content=await pdf_service.read_and_validate_upload(file)
    finally:
        await file.close()
    key = (client_id, x_upload_id)
    if x_upload_id:
        with _progress_lock:
            if key in _progress:
                raise HTTPException(409, "Upload ID already in use")
            _progress[key] = {"stage": "waiting"}

    def report(stage, current, total, page):
        if x_upload_id:
            with _progress_lock:
                _progress[key] = dict(stage=stage, current=current, total=total, page=page)

    try:
        return await run_in_threadpool(_save_document, content, file.filename, client_id, report)
    finally:
        if x_upload_id:
            with _progress_lock:
                _progress.pop(key, None)


def _save_document(content, filename, client_id, report):
    extracted=pdf_service.extract_pages(content, report)
    original_name=storage.sanitize_filename(filename or "document.pdf")
    stored_name,_path=storage.save_upload(content)
    try:
        with write() as conn:
            cur=conn.execute("""INSERT INTO documents(client_id, filename, stored_name, size, page_count)
                   VALUES (?,?,?,?,?)""",(client_id,original_name,stored_name,len(content),extracted.page_count))
            doc_id=cur.lastrowid
            created_at=conn.execute("SELECT created_at FROM documents WHERE id=?", (doc_id,)).fetchone()["created_at"]
            conn.executemany("INSERT INTO pages(document_id, page_num, text) VALUES (?,?,?)",
                             [(doc_id,i+1,t) for i,t in enumerate(extracted.pages)])
    except Exception:
        storage.delete_upload(stored_name); raise
    return DocumentDetailOut(id=doc_id,filename=original_name,size=len(content),page_count=extracted.page_count,
        status="ready",created_at=created_at,warnings=extracted.warnings,
        pages=[PagePreview(page_num=i+1,text_preview=_preview(t)) for i,t in enumerate(extracted.pages)])

@router.get("",response_model=list[DocumentOut])
def list_documents(client_id:str=Depends(ensure_client)):
    with read() as conn:
        rows=conn.execute("""SELECT id, filename, size, page_count, status, created_at
               FROM documents WHERE client_id=? ORDER BY id DESC""",(client_id,)).fetchall()
    return [DocumentOut(**dict(r)) for r in rows]

@router.get("/{doc_id}",response_model=DocumentDetailOut)
def get_document(doc_id:int,client_id:str=Depends(ensure_client)):
    with read() as conn:
        doc=conn.execute("SELECT * FROM documents WHERE id=? AND client_id=?",(doc_id,client_id)).fetchone()
        if not doc: raise HTTPException(404,"Document not found")
        pages=conn.execute("SELECT page_num, text FROM pages WHERE document_id=? ORDER BY page_num",(doc_id,)).fetchall()
    return DocumentDetailOut(id=doc["id"],filename=doc["filename"],size=doc["size"],page_count=doc["page_count"],
        status=doc["status"],created_at=doc["created_at"],
        pages=[PagePreview(page_num=p["page_num"],text_preview=_preview(p["text"])) for p in pages])

@router.delete("/{doc_id}",status_code=204)
def delete_document(doc_id:int,client_id:str=Depends(ensure_client)):
    with write() as conn:
        doc=conn.execute("SELECT stored_name FROM documents WHERE id=? AND client_id=?",(doc_id,client_id)).fetchone()
        if not doc: raise HTTPException(404,"Document not found")
        if conn.execute(
            "SELECT 1 FROM jobs WHERE document_id=? AND status IN ('pending','running')", (doc_id,)
        ).fetchone():
            raise HTTPException(409, "Wait for generation to finish before deleting this document")
        conn.execute("DELETE FROM documents WHERE id=?",(doc_id,))
    storage.delete_upload(doc["stored_name"])
    return None

def _preview(text:str,limit:int=400)->str:
    text=" ".join((text or "").split())
    return text if len(text)<=limit else text[:limit].rsplit(" ",1)[0]+"…"
