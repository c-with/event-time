"""AUDIT-03 R2-C regression tests: SEC-05 / DATA-02 / SEC-04.

Run: python -m unittest discover -s tests -v
Covers the three R2-C fixes — structured 409 detail, archive revision guard,
and /health error hygiene.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import IntegrityError

from app import create_app, db, init_database
from models import Project


class R2CRegressionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db_path = Path(self.temp.name) / "test.sqlite3"
        self.env = patch.dict(os.environ, {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SHARED_PASSWORD": "test-only-password-strong-123",
            "SHARED_USERNAME": "activity",
            "SESSION_SECRET": "test-session-secret-strong-123",
        })
        self.env.start()
        self.app = create_app({"TESTING": True})
        # Probe routes must be registered before the first request (setUp logs in below).
        self.app.add_url_rule("/__probe_sqlite", "probe_sqlite", self._raise_sqlite_integrity)
        self.app.add_url_rule("/__probe_postgres", "probe_postgres", self._raise_postgres_integrity)
        init_database(self.app)
        self.client = self.app.test_client()
        login = self.client.post("/api/login", json={
            "username": "activity", "password": "test-only-password-strong-123"
        })
        self.assertEqual(login.status_code, 200, login.get_json())
        self.headers = {"X-CSRF-Token": login.get_json()["csrf_token"],
                        "X-Operator-Name": "R2C回归测试"}

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def make_project(self, name):
        response = self.client.post("/api/projects", json={"name": name}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["project"]

    def _raise_sqlite_integrity(self):
        raise IntegrityError(
            "INSERT INTO clients (name) VALUES ('重复客户')",
            None,
            Exception("UNIQUE constraint failed: clients.name"))

    def _raise_postgres_integrity(self):
        orig = Exception('insert or update on table "requirements" violates '
                         'foreign key constraint "requirements_work_package_id_fkey"')
        orig.sqlstate = "23503"
        raise IntegrityError('INSERT INTO requirements ("work_package_id") VALUES (1)', None, orig)

    # SEC-05：IntegrityError 409 只返結構化 kind，唔洩漏 SQL／驅動原文

    def test_integrity_error_returns_structured_detail_without_raw_sql(self):
        sqlite_response = self.client.get("/__probe_sqlite")
        self.assertEqual(sqlite_response.status_code, 409)
        sqlite_body = sqlite_response.get_data(as_text=True)
        self.assertEqual(sqlite_response.get_json()["detail"], {"kind": "duplicate"})
        self.assertNotIn("INSERT INTO", sqlite_body)
        self.assertNotIn("UNIQUE constraint failed", sqlite_body)

        pg_response = self.client.get("/__probe_postgres")
        self.assertEqual(pg_response.status_code, 409)
        pg_body = pg_response.get_data(as_text=True)
        self.assertEqual(pg_response.get_json()["detail"], {"kind": "foreign_key"})
        self.assertNotIn("violates foreign key", pg_body)
        self.assertNotIn("INSERT INTO", pg_body)

    # DATA-02：/archive 必須帶 _revision 並比對，stale 一律 409

    def test_archive_with_stale_revision_is_rejected(self):
        project = self.make_project("并发归档项目")
        stale_revision = project["revision"]
        bump = self.client.patch(f"/api/projects/{project['id']}", json={
            "_revision": stale_revision, "description": "另一台设备的修改",
        }, headers=self.headers)
        self.assertEqual(bump.status_code, 200, bump.get_json())
        current_revision = bump.get_json()["revision"]

        response = self.client.post(f"/api/projects/{project['id']}/archive", json={
            "confirm": True, "_revision": stale_revision,
        }, headers=self.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        body = response.get_json()
        self.assertEqual(body["revision"], current_revision)
        conflict = body["conflicts"][0]
        self.assertEqual(conflict["field"], "phase")
        self.assertEqual(conflict["incoming"], "已归档")
        self.assertIn("current", conflict)
        with self.app.app_context():
            entity = db.session.get(Project, project["id"])
            self.assertNotEqual(entity.phase, "已归档")
            self.assertIsNone(entity.archived_at)

    def test_archive_with_fresh_revision_succeeds(self):
        project = self.make_project("正常归档项目")
        response = self.client.post(f"/api/projects/{project['id']}/archive", json={
            "confirm": True, "_revision": project["revision"],
        }, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["project"]["phase"], "已归档")
        with self.app.app_context():
            entity = db.session.get(Project, project["id"])
            self.assertEqual(entity.phase, "已归档")
            self.assertIsNotNone(entity.archived_at)
            self.assertEqual(entity.revision, project["revision"] + 1)

    def test_archive_without_revision_is_rejected(self):
        project = self.make_project("缺版本归档项目")
        response = self.client.post(f"/api/projects/{project['id']}/archive", json={
            "confirm": True,
        }, headers=self.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        with self.app.app_context():
            entity = db.session.get(Project, project["id"])
            self.assertNotEqual(entity.phase, "已归档")

    # SEC-04：/health 失敗時只返通用訊息（503 語義不變），原文入 log

    def test_health_failure_returns_generic_message(self):
        fake_db = MagicMock()
        fake_db.session.execute.side_effect = Exception(
            'connection to server at "10.1.2.3", port 5432 failed: '
            'FATAL: password authentication failed for user "activity_workbench_app"')
        with patch("app.db", fake_db):
            response = self.client.get("/health")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["ok"])
        self.assertNotIn("password authentication failed", body)
        self.assertNotIn("10.1.2.3", body)

    def test_health_ok_path_unchanged(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["database"], "sqlite-test")


if __name__ == "__main__":
    unittest.main()
