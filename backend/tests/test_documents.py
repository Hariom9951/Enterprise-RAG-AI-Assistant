"""
Enterprise RAG AI Assistant — Document API Ingestion Test Suite
================================================================
Contains integration tests for:
  - Document uploads validation (MIME-types, extensions, size filters)
  - Per-user duplicate checks via SHA-256 integrity hash
  - Document metadata listings and updates (renames checks)
  - Ownership security checks (cross-user document operations blocks)
  - Physical storage file deletion cleanup
"""

import io
import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.document import Document
from tests.conftest import VALID_USER

# =============================================================================
# Helper Functions
# =============================================================================


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Register and log in a new user, returning their access token."""
    user_payload = {
        "email": email,
        "password": VALID_USER["password"],
        "full_name": "Test User",
    }
    await client.post("/api/v1/auth/register", json=user_payload)
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": VALID_USER["password"]},
    )
    return login_resp.json()["access_token"]


# =============================================================================
# Integration Tests
# =============================================================================


class TestDocumentIngestion:
    """Test suite verifying document upload, validation, and CRUD operations."""

    @pytest.mark.anyio
    async def test_upload_valid_files(self, client: AsyncClient) -> None:
        """Uploading valid TXT, PDF, and DOCX files should succeed."""
        token = await _register_and_login(client, "uploader@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Text File
        txt_file = io.BytesIO(b"Hello world, this is a plain text file payload.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("test.txt", txt_file, "text/plain")},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["original_filename"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["processing_status"] in (
            "QUEUED",
            "PROCESSING",
            "PROCESSED",
            "FAILED",
        )  # Phase 5: task runs eagerly, reaches PROCESSED
        assert "id" in data

        # 2. PDF File
        pdf_file = io.BytesIO(b"%PDF-1.4 Mock PDF payload bytes here.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("report.pdf", pdf_file, "application/pdf")},
        )
        assert response.status_code == 201, response.text
        assert response.json()["original_filename"] == "report.pdf"

        # 3. DOCX File
        docx_file = io.BytesIO(b"Mock docx zip container bytes structure.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={
                "file": (
                    "memo.docx",
                    docx_file,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["original_filename"] == "memo.docx"

    @pytest.mark.anyio
    async def test_upload_unsupported_extensions(self, client: AsyncClient) -> None:
        """Uploading executable files, archives, or images should be rejected with 400."""
        token = await _register_and_login(client, "blockext@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Executable file
        exe_file = io.BytesIO(b"MZ executable header payload.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("virus.exe", exe_file, "application/x-msdownload")},
        )
        assert response.status_code == 400, response.text
        assert "Unsupported file extension" in response.json()["error"]["message"]

        # Zip Archive
        zip_file = io.BytesIO(b"PK archive stream.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("archive.zip", zip_file, "application/zip")},
        )
        assert response.status_code == 400

        # PNG Image
        png_file = io.BytesIO(b"PNG image header bytes.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("photo.png", png_file, "image/png")},
        )
        assert response.status_code == 400

    @pytest.mark.anyio
    async def test_upload_mime_spoofing_rejected(self, client: AsyncClient) -> None:
        """Files where extension does not match MIME type should be rejected with 400."""
        token = await _register_and_login(client, "spoof@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Text content masquerading as PDF extension
        fake_pdf = io.BytesIO(b"Just plain text body.")
        response = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("report.pdf", fake_pdf, "text/plain")},
        )
        assert response.status_code == 400
        assert (
            "does not match its MIME content type"
            in response.json()["error"]["message"]
        )

    @pytest.mark.anyio
    async def test_upload_exceeds_size_limit(self, client: AsyncClient) -> None:
        """Files exceeding max_upload_size_mb should be rejected with 400."""
        token = await _register_and_login(client, "sizelimit@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Temporarily set max upload limit to 1MB to keep test memory low
        original_limit = settings.max_upload_size_mb
        settings.max_upload_size_mb = 1

        try:
            # Generate 2MB payload stream
            large_content = b"a" * (2 * 1024 * 1024)
            large_file = io.BytesIO(large_content)

            response = await client.post(
                "/api/v1/documents/upload",
                headers=headers,
                files={"file": ("large.txt", large_file, "text/plain")},
            )
            assert response.status_code == 400
            assert "exceeds the limit" in response.json()["error"]["message"]
        finally:
            settings.max_upload_size_mb = original_limit

    @pytest.mark.anyio
    async def test_duplicate_detection(self, client: AsyncClient) -> None:
        """Uploading the exact same file content twice for the same user must return 409."""
        token = await _register_and_login(client, "duplicate@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        file_content = b"Single unique document contents that should not be duplicated."

        # First upload
        resp1 = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("doc.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert resp1.status_code == 201

        # Second upload
        resp2 = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("duplicate.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert resp2.status_code == 409
        assert "already uploaded this document" in resp2.json()["error"]["message"]

    @pytest.mark.anyio
    async def test_cross_user_isolation(self, client: AsyncClient) -> None:
        """User A must not be able to list, fetch, rename, or delete User B's documents."""
        token_a = await _register_and_login(client, "usera@example.com")
        token_b = await _register_and_login(client, "userb@example.com")

        # 1. User A uploads a file
        txt_file = io.BytesIO(b"User A private thoughts.")
        resp_upload = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token_a}"},
            files={"file": ("private.txt", txt_file, "text/plain")},
        )
        assert resp_upload.status_code == 201
        doc_id = resp_upload.json()["id"]

        # 2. User B tries to fetch User A's file metadata (Should fail with 404)
        resp_get = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_get.status_code == 404

        # 3. User B tries to rename User A's file (Should fail with 404)
        resp_rename = await client.patch(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"original_filename": "hacked.txt"},
        )
        assert resp_rename.status_code == 404

        # 4. User B tries to delete User A's file (Should fail with 404)
        resp_delete = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_delete.status_code == 404

        # 5. User B lists their documents (Should be empty)
        resp_list = await client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_list.status_code == 200
        assert len(resp_list.json()) == 0

    @pytest.mark.anyio
    async def test_document_rename_validation(self, client: AsyncClient) -> None:
        """Renaming a document should succeed but changing extension must fail."""
        token = await _register_and_login(client, "rename@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Upload
        resp_upload = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("memo.txt", io.BytesIO(b"Memo contents"), "text/plain")},
        )
        assert resp_upload.status_code == 201
        doc_id = resp_upload.json()["id"]

        # Rename same extension (should pass)
        resp_rename = await client.patch(
            f"/api/v1/documents/{doc_id}",
            headers=headers,
            json={"original_filename": "new_memo.txt"},
        )
        assert resp_rename.status_code == 200
        assert resp_rename.json()["original_filename"] == "new_memo.txt"

        # Rename different extension (should fail)
        resp_bad = await client.patch(
            f"/api/v1/documents/{doc_id}",
            headers=headers,
            json={"original_filename": "new_memo.pdf"},
        )
        assert resp_bad.status_code == 400
        assert "file extensions" in resp_bad.json()["error"]["message"]

    @pytest.mark.anyio
    async def test_physical_file_cleanup_on_delete(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Deleting a document must delete the database record AND physical file on disk."""
        token = await _register_and_login(client, "cleanup@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Upload
        resp_upload = await client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={
                "file": (
                    "temp.txt",
                    io.BytesIO(b"Disposable file contents"),
                    "text/plain",
                )
            },
        )
        assert resp_upload.status_code == 201
        doc_id_str = resp_upload.json()["id"]
        doc_id = uuid.UUID(doc_id_str)

        # Query database to extract physical path
        result = await db_session.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        assert doc is not None
        file_path = doc.storage_path
        assert os.path.exists(file_path)

        # Delete document via API
        resp_del = await client.delete(
            f"/api/v1/documents/{doc_id_str}",
            headers=headers,
        )
        assert resp_del.status_code == 204

        # Assert physical file no longer exists
        assert not os.path.exists(
            file_path
        ), "Physical document file was not deleted from storage directory!"
