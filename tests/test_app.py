"""Automatic tests for StudyForge critical logic."""
import io, os, tempfile
_tmp=tempfile.mkdtemp(prefix="studyforge_test_")
os.environ["STUDYFORGE_DATA_DIR"]=_tmp
os.environ["LLM_PROVIDER"]="mock"
os.environ["WEEKLY_TOKEN_LIMIT"]="100000"
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.config import settings
from app.db import init_db
from app.main import app
init_db()
client=TestClient(app); client2=TestClient(app)

def make_pdf(pages):
    buf=io.BytesIO(); c=canvas.Canvas(buf)
    for text in pages:
        if text: c.drawString(72,720,text)
        c.showPage()
    c.save(); return buf.getvalue()

LECTURE=make_pdf(["Photosynthesis converts light energy into chemical energy stored in glucose molecules.",
"The Calvin cycle takes place in the stroma of the chloroplast and fixes carbon dioxide.",
"Cellular respiration breaks down glucose to produce ATP in the mitochondria."])

def _upload(data=LECTURE,filename="lecture.pdf",ctype="application/pdf"):
    return client.post("/api/documents",files={"file":(filename,data,ctype)})
def _generate(doc_id,mtype,p_from=1,p_to=3):
    r=client.post("/api/generations",json={"document_id":doc_id,"page_from":p_from,"page_to":p_to,"material_type":mtype})
    assert r.status_code==201,r.text; return r.json()
def _wait_job(job_id):
    for _ in range(50):
        j=client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done","error"): return j
    raise AssertionError("job did not finish")

def test_health(): assert client.get("/api/health").status_code==200
def test_upload_ok():
    r=_upload(); assert r.status_code==201; b=r.json(); assert b["page_count"]==3; assert len(b["pages"])==3; assert b["pages"][0]["text_preview"]
def test_upload_rejects_non_pdf(): assert _upload(b"hello world","notes.txt","text/plain").status_code==415
def test_upload_rejects_fake_pdf(): assert _upload(b"%PDF-not really a pdf","fake.pdf").status_code==422
def test_upload_rejects_blank_pdf(): assert _upload(make_pdf(["","",""]),"blank.pdf").status_code==422
def test_filename_sanitized_against_path_traversal():
    r=_upload(filename="../../evil.pdf"); assert r.status_code==201; assert "/" not in r.json()["filename"]; assert ".." not in r.json()["filename"]
def test_client_isolation():
    doc_id=_upload().json()["id"]; assert client2.get(f"/api/documents/{doc_id}").status_code==404; assert client2.get("/api/generations").json()==[]; assert client.get(f"/api/documents/{doc_id}").status_code==200
def test_generate_summary_end_to_end():
    doc_id=_upload().json()["id"]; j=_wait_job(_generate(doc_id,"summary")["job_id"]); assert j["status"]=="done",j; gen=j["generation"]; assert gen["result"]["sections"]; q=client.get("/api/quota").json(); assert q["used"]>0; assert q["remaining"]==q["limit"]-q["used"]
def test_generation_idempotent_no_extra_tokens():
    doc_id=_upload().json()["id"]; j1=_wait_job(_generate(doc_id,"flashcards")["job_id"]); assert j1["status"]=="done"; used=client.get("/api/quota").json()["used"]; again=_generate(doc_id,"flashcards"); assert again["status"]=="existing"; assert again["generation"]["id"]==j1["generation"]["id"]; assert client.get("/api/quota").json()["used"]==used
def test_invalid_range_rejected():
    doc_id=_upload().json()["id"]; assert client.post("/api/generations",json={"document_id":doc_id,"page_from":2,"page_to":1,"material_type":"quiz"}).status_code==400; assert client.post("/api/generations",json={"document_id":doc_id,"page_from":1,"page_to":99,"material_type":"quiz"}).status_code==400
def test_weekly_limit_enforced():
    doc_id=_upload().json()["id"]; old=settings.WEEKLY_TOKEN_LIMIT
    try:
        settings.WEEKLY_TOKEN_LIMIT=1; j=_wait_job(_generate(doc_id,"quiz")["job_id"]); assert j["status"]=="error"; assert "limit" in j["error"].lower(); assert client.get(f"/api/generations?document_id={doc_id}").json()==[]
    finally: settings.WEEKLY_TOKEN_LIMIT=old
    j2=_wait_job(_generate(doc_id,"quiz")["job_id"]); assert j2["status"]=="done"
def test_quiz_structure_validated():
    doc_id=_upload().json()["id"]; j=_wait_job(_generate(doc_id,"quiz")["job_id"]); assert j["status"]=="done"
    for q in j["generation"]["result"]["questions"]: assert len(q["options"])==4; assert 0<=q["correct_index"]<=3
def test_list_and_get_generation_access_control():
    doc_id=_upload().json()["id"]; j=_wait_job(_generate(doc_id,"summary")["job_id"]); gid=j["generation"]["id"]; assert any(g["id"]==gid for g in client.get("/api/generations").json()); assert client.get(f"/api/generations/{gid}").json()["id"]==gid; assert client2.get(f"/api/generations/{gid}").status_code==404
def test_usage_helpers():
    from app.services.usage import estimate_tokens,current_week_start,get_quota
    assert estimate_tokens("abcd")>=1; assert len(current_week_start())==10; assert get_quota("nobody")["used"]==0
