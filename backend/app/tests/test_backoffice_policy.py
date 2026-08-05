import unittest
from uuid import uuid4

from app.backoffice.models import PlanStep, TaskPlan
from app.backoffice.policy import ExecutionNotAvailable, assert_planning_only


class BackofficePolicyTests(unittest.TestCase):
    def test_execution_is_unavailable_in_m09(self) -> None:
        safe = TaskPlan(uuid4(), (PlanStep("Prepare", True),), True)
        assert_planning_only(safe)
        unsafe = TaskPlan(uuid4(), (PlanStep("Execute", True, execution_authority=True),), True)
        with self.assertRaises(ExecutionNotAvailable):
            assert_planning_only(unsafe)
