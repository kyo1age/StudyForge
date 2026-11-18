"""Release regressions use synthetic data and never call an external provider."""
import logging

import pytest

from .test_app import LECTURE, _generate, _upload, _wait_job, client
from app.services import jobs


def test_untrusted_host_is_rejected():
    assert client.get('/api/health', headers={'Host': 'attacker.invalid'}).status_code == 400


@pytest.mark.parametrize('host', ['127.0.0.1:8001', 'localhost:8001', '[::1]:8001'])
def test_loopback_hosts_remain_available(host):
    assert client.get('/api/health', headers={'Host': host}).status_code == 200


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://attacker.invalid'},
    {'Origin': 'null'},
    {'Sec-Fetch-Site': 'cross-site'},
    {'Origin': 'http://127.0.0.1:9000'},
    {'Origin': 'http://localhost'},
])
def test_cross_origin_upload_is_rejected_before_processing(headers):
    response = client.post('/api/documents', headers=headers,
                           files={'file': ('synthetic.pdf', LECTURE, 'application/pdf')})
    assert response.status_code == 403


def test_same_origin_upload_remains_available():
    response = client.post('/api/documents', headers={'Origin': 'http://127.0.0.1'},
                           files={'file': ('synthetic.pdf', LECTURE, 'application/pdf')})
    assert response.status_code == 201
    assert response.headers['cache-control'] == 'no-store'
    assert client.get(f"/api/documents/{response.json()['id']}").headers['cache-control'] == 'no-store'


def test_unexpected_provider_error_does_not_log_sensitive_details(monkeypatch, caplog):
    class FailingProvider:
        name = 'mock'

        def generate(self, *args):
            raise RuntimeError('PRIVATE_DOCUMENT_CANARY')

    monkeypatch.setattr(jobs, 'get_llm', FailingProvider)
    with caplog.at_level(logging.ERROR, logger='app.services.jobs'):
        job = _wait_job(_generate(_upload().json()['id'], 'summary')['job_id'])
    assert job['status'] == 'error'
    assert 'PRIVATE_DOCUMENT_CANARY' not in str(job)
    assert 'PRIVATE_DOCUMENT_CANARY' not in caplog.text
    assert 'RuntimeError' in caplog.text


@pytest.mark.parametrize('path', ['/.env', '/data/studyforge.db', '/app/config.py'])
def test_private_files_are_not_served(path):
    assert client.get(path).status_code == 404


def test_pdf_page_and_text_limits(monkeypatch):
    from .test_app import settings
    monkeypatch.setattr(settings, 'MAX_PDF_PAGES', 2)
    assert _upload().status_code == 422
    monkeypatch.setattr(settings, 'MAX_PDF_PAGES', 500)
    monkeypatch.setattr(settings, 'MAX_EXTRACTED_CHARS', 10)
    assert _upload().status_code == 422


def test_ocr_timeout_cleans_temporary_pdf(monkeypatch, tmp_path):
    import subprocess
    from .test_app import make_pdf, settings
    from app.services import ocr
    monkeypatch.setattr(settings, 'OCR_TESSDATA_DIR', tmp_path)
    for language in ocr.LANGUAGES:
        (tmp_path / f'{language}.traineddata').touch()
    before = set(settings.DATA_DIR.glob('ocr-*'))

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('synthetic-worker', 1)

    monkeypatch.setattr(ocr.subprocess, 'run', timeout)
    response = _upload(make_pdf(['']))
    assert response.status_code == 422
    assert set(settings.DATA_DIR.glob('ocr-*')) == before
    assert 'synthetic-worker' not in response.text


def test_ocr_worker_does_not_receive_provider_credentials(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.services import ocr
    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.setenv(name, 'synthetic-private-value')
    observed = []

    def run(command, **kwargs):
        observed.append(command)
        assert not {'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY'} & kwargs['env'].keys()
        assert not kwargs.get('shell', False)
        return SimpleNamespace(stdout=b'synthetic OCR text')

    monkeypatch.setattr(ocr.subprocess, 'run', run)
    assert ocr._recognize(tmp_path / 'input.pdf', 0, 1) == 'synthetic OCR text'
    assert len(observed) == 1
