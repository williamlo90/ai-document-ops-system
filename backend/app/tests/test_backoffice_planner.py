import unittest
from uuid import uuid4

from app.backoffice.models import WorkItem
from app.backoffice.planner import build_plan


class BackofficePlannerTests(unittest.TestCase):
    def test_plan_is_deterministic_and_has_no_execution_authority(self) -> None:
        item = WorkItem("alpha", "Review invoice", uuid4())
        first = build_plan(item)
        second = build_plan(item)
        self.assertEqual(first.steps, second.steps)
        self.assertTrue(first.requires_approval)
        self.assertFalse(any(step.execution_authority for step in first.steps))
