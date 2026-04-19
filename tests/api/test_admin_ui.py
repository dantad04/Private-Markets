from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding, SourceFile
from app.db.session import get_engine
from tests.hesta_fixture import EXPECTED_TOTAL_ROWS, FIXTURE_PATH


class TestAdminUi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage1_admin_ui.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.app = create_app()

        def override_get_db_session():
            session = self.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.app.dependency_overrides[get_db_session] = override_get_db_session
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_source_files_list_page_renders(self) -> None:
        response = self.client.get("/admin/ui/source-files")
        self.assertEqual(200, response.status_code)
        self.assertIn("<title>Source Files - Private Market Insider: Australia</title>", response.text)

    def test_source_files_list_shows_ingested_hesta_row_and_rows_loaded(self) -> None:
        self.client.post(
            "/admin/ingest/local-file",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
            },
        )

        response = self.client.get("/admin/ui/source-files")
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.text.count("/admin/ui/source-files/"))
        self.assertIn(">hesta<", response.text)
        self.assertIn(f">{EXPECTED_TOTAL_ROWS}<", response.text)

    def test_source_file_detail_contains_known_holding(self) -> None:
        self.client.post(
            "/admin/ingest/local-file",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
            },
        )

        with self.SessionLocal() as session:
            source_file_id = session.scalar(select(SourceFile.id).limit(1))

        response = self.client.get(f"/admin/ui/source-files/{source_file_id}")
        self.assertEqual(200, response.status_code)
        self.assertIn("JPMorgan Chase &amp; Co", response.text)

    def test_upload_form_posts_and_redirects_with_flash_message(self) -> None:
        response = self.client.post(
            "/admin/ui/ingest",
            data={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
                "publication_date": "",
                "reporting_period_id": "",
            },
            follow_redirects=True,
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(
            f"Ingest succeeded. rows_inserted={EXPECTED_TOTAL_ROWS} rows_skipped_existing=0 warnings=",
            response.text,
        )
        with self.SessionLocal() as session:
            rows_loaded = session.scalar(select(func.count(Holding.id)))
        self.assertEqual(EXPECTED_TOTAL_ROWS, rows_loaded)
