from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bot.napcat_admin import ensure_projects, read_target

PROJECTS = [
    {"key": "mocha", "name": "青叶摩卡httpc", "url": "http://127.0.0.1:8080/event", "token": "a"},
    {"key": "companion", "name": "陪伴工作台", "url": "http://127.0.0.1:8765/napcat/event", "token": "b"},
]


class NapCatAdminTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="napcat-admin-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_one_project_is_enabled(self):
        data = {"network": {"httpClients": []}}
        ensure_projects(data, PROJECTS, "companion")
        clients = data["network"]["httpClients"]
        self.assertEqual(len(clients), 2)
        self.assertEqual(
            [c["name"] for c in clients if c["enable"]], ["陪伴工作台"],
        )
        self.assertEqual(read_target(data, PROJECTS), "companion")

        ensure_projects(data, PROJECTS, "mocha")
        self.assertEqual(
            [c["name"] for c in clients if c["enable"]], ["青叶摩卡httpc"],
        )
        self.assertEqual(read_target(data, PROJECTS), "mocha")

    def test_existing_clients_are_updated_not_duplicated(self):
        data = {"network": {"httpClients": [
            {"name": "青叶摩卡httpc", "enable": False,
             "url": "http://127.0.0.1:8080/event?token=old", "token": "old"},
        ]}}
        ensure_projects(data, PROJECTS, "mocha")
        self.assertEqual(len(data["network"]["httpClients"]), 2)
        self.assertTrue(data["network"]["httpClients"][0]["enable"])


if __name__ == "__main__":
    unittest.main()
