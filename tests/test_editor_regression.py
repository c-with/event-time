"""HTTP regression tests for V0.4.1 relation updates and atomic failure.

Run: python -m unittest discover -s tests -v
These use a disposable SQLite DB; PostgreSQL/browser verification remains separate.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app, db, init_database
from models import Project, Task, RequirementItem, TaskDependency, FieldRevision


class RelationsRegressionTest(unittest.TestCase):
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
        init_database(self.app)
        self.client = self.app.test_client()
        login = self.client.post("/api/login", json={
            "username": "activity", "password": "test-only-password-strong-123"
        })
        self.assertEqual(login.status_code, 200, login.get_json())
        self.headers = {"X-CSRF-Token": login.get_json()["csrf_token"],
                        "X-Operator-Name": "审计回归测试"}
        self.project_id = self.create("/api/projects", {"name": "回归项目"})["project"]["id"]

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def create(self, url, data):
        response = self.client.post(url, json=data, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def make_task(self, name):
        return self.create(f"/api/projects/{self.project_id}/tasks",
                           {"name": name})["task"]

    def test_task_edit_and_relations_are_atomic(self):
        prereq = self.make_task("前置任务")
        task = self.make_task("执行任务")
        requirement = self.create(f"/api/projects/{self.project_id}/requirements",
                                  {"name": "背景板"})["requirement"]
        response = self.client.patch(f"/api/tasks/{task['id']}", json={
            "_revision": task["revision"], "name": "更新执行任务",
            "dependency_ids": [prereq["id"]],
            "requirement_ids": [requirement["id"]],
        }, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        with self.app.app_context():
            entity = db.session.get(Task, task["id"])
            self.assertEqual(entity.name, "更新执行任务")
            self.assertEqual({x.depends_on_task_id for x in entity.dependencies}, {prereq["id"]})
            self.assertEqual({x.id for x in entity.requirements}, {requirement["id"]})
            changed = db.session.query(FieldRevision).filter(
                FieldRevision.entity_type == "tasks",
                FieldRevision.entity_id == task["id"],
                FieldRevision.field_path == "dependency_ids").all()
            self.assertTrue(changed)

    def test_invalid_relationship_does_not_save_valid_scalar(self):
        task = self.make_task("原始名称")
        response = self.client.patch(f"/api/tasks/{task['id']}", json={
            "_revision": task["revision"], "name": "不该保存的名称",
            "requirement_ids": ["unknown-requirement-id"],
        }, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            entity = db.session.get(Task, task["id"])
            self.assertEqual(entity.name, "原始名称")
            self.assertEqual(entity.revision, task["revision"])

    def test_stale_relationship_edit_is_rejected(self):
        task = self.make_task("并发任务")
        initial = task["revision"]
        first = self.client.patch(f"/api/tasks/{task['id']}", json={
            "_revision": initial, "notes": "先修改",
        }, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.get_json())
        second = self.client.patch(f"/api/tasks/{task['id']}", json={
            "_revision": initial, "dependency_ids": [],
        }, headers=self.headers)
        self.assertEqual(second.status_code, 409, second.get_json())

    def test_missing_csrf_cannot_edit(self):
        task = self.make_task("CSRF任务")
        result = self.client.patch(f"/api/tasks/{task['id']}",
                                   json={"notes": "不允许"},
                                   headers={"X-Operator-Name": "审计回归测试"})
        self.assertEqual(result.status_code, 403)


if __name__ == "__main__":
    unittest.main()
