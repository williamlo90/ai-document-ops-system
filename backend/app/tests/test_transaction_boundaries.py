from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.dependencies import AppContainer, build_container
from app.backoffice.models import ActionStepStatus, ActionType, WorkItemStatus, WorkType
from app.backoffice.planner import PlanningInput
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.exports.models import (
    ExportBatchRecord,
    ExportBatchStatus,
    ExportEligibilityError,
    ExportRunRecord,
    ExportRunStatus,
)
from app.main import create_app
from app.providers.contracts import ExtractionResult
from app.validation.invoice import ValidationReport


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class TransactionBoundaryTests(unittest.TestCase):
    def test_hosted_mode_rejects_disposable_memory_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hosted = Settings(
                app_env="production",
                admin_token="admin-token-with-24-characters",
                metrics_token="metrics-token-with-24-characters",
                upload_root=root / "uploads",
                max_upload_bytes=1_000,
                storage_backend="memory",
            )
            with self.assertRaisesRegex(
                ValueError,
                "Hosted mode requires persistent sqlite storage",
            ):
                build_container(hosted)

            local = replace(hosted, app_env="local")
            container = build_container(local)
            container.close()

    def test_backoffice_plan_writes_roll_back_at_each_repository_boundary(self) -> None:
        injection_points = {
            "agent_run": ("agent_runs", "add"),
            "plan": ("backoffice_plans", "save"),
            "event": ("workflow_events", "add"),
            "policy_decision": ("backoffice_policy_decisions", "add"),
            "draft": ("backoffice_drafts", "save"),
            "approval": ("backoffice_approvals", "save"),
        }
        for label, (repository_name, method_name) in injection_points.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                container = build_container(self._settings(temp_dir))
                try:
                    work_item = container.backoffice_service.create_work_item(
                        title="Export approved invoice",
                        context=self._context(),
                        work_type=WorkType.INVOICE_EXPORT,
                    )
                    repository = getattr(container, repository_name)
                    original = getattr(repository, method_name)

                    def fail_after_write(
                        *args,
                        _original=original,
                        _label=label,
                        **kwargs,
                    ):
                        _original(*args, **kwargs)
                        raise RuntimeError(f"injected {_label} write failure")

                    with (
                        patch.object(
                            repository,
                            method_name,
                            side_effect=fail_after_write,
                        ),
                        self.assertRaisesRegex(
                            RuntimeError,
                            f"injected {label} write failure",
                        ),
                    ):
                        container.backoffice_service.plan_work_item(
                            work_item_id=work_item.id,
                            context=self._context(),
                            planning_input=PlanningInput(
                                requested_outcome="export invoice",
                                approved_for_export=True,
                            ),
                            idempotency_key=f"plan-{label}",
                        )

                    persisted = container.backoffice_work_items.get(work_item.id)
                    self.assertIsNone(persisted.current_plan_id)
                    self.assertEqual(
                        container.backoffice_plans.list_for_work_item(
                            "default",
                            work_item.id,
                        ),
                        [],
                    )
                    self.assertEqual(
                        container.backoffice_drafts.list_for_work_item(
                            "default",
                            work_item.id,
                        ),
                        [],
                    )
                    self.assertEqual(
                        container.backoffice_approvals.list_for_work_item(
                            "default",
                            work_item.id,
                        ),
                        [],
                    )
                    self.assertEqual(
                        container.backoffice_policy_decisions.list_for_work_item(
                            "default",
                            work_item.id,
                        ),
                        [],
                    )
                    self.assertEqual(
                        container.agent_runs.list_recent("default"),
                        [],
                    )
                    events = container.workflow_events.list_for_work_item(
                        "default",
                        work_item.id,
                    )
                    self.assertEqual(
                        [event.event_type for event in events],
                        ["work_item_created"],
                    )
                finally:
                    container.close()

    def test_backoffice_idempotency_is_serialized_across_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            first = build_container(settings)
            second = build_container(settings)
            create_barrier = threading.Barrier(2)
            created = []
            errors: list[Exception] = []
            try:

                def create(service) -> None:
                    try:
                        create_barrier.wait(timeout=5)
                        created.append(
                            service.create_work_item(
                                title="Concurrent export",
                                context=self._context(),
                                work_type=WorkType.INVOICE_EXPORT,
                                idempotency_key="concurrent-create",
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                threads = [
                    threading.Thread(target=create, args=(first.backoffice_service,)),
                    threading.Thread(target=create, args=(second.backoffice_service,)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

                self.assertEqual(errors, [])
                self.assertEqual(len(created), 2)
                self.assertEqual(created[0].id, created[1].id)
                self.assertEqual(
                    len(first.backoffice_work_items.list_by_workspace("default")),
                    1,
                )

                plan_barrier = threading.Barrier(2)
                planned = []

                def plan(service) -> None:
                    try:
                        plan_barrier.wait(timeout=5)
                        planned.append(
                            service.plan_work_item(
                                work_item_id=created[0].id,
                                context=self._context(),
                                planning_input=PlanningInput(
                                    requested_outcome="export invoice",
                                    approved_for_export=True,
                                ),
                                idempotency_key="concurrent-plan",
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                threads = [
                    threading.Thread(target=plan, args=(first.backoffice_service,)),
                    threading.Thread(target=plan, args=(second.backoffice_service,)),
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

                self.assertEqual(errors, [])
                self.assertEqual(len(planned), 2)
                self.assertEqual(planned[0].plan_id, planned[1].plan_id)
                self.assertEqual(
                    len(
                        first.backoffice_plans.list_for_work_item(
                            "default",
                            created[0].id,
                        )
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        first.backoffice_drafts.list_for_work_item(
                            "default",
                            created[0].id,
                        )
                    ),
                    1,
                )
                self.assertEqual(
                    len(
                        first.backoffice_approvals.list_for_work_item(
                            "default",
                            created[0].id,
                        )
                    ),
                    1,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "idempotency key is already bound to a different request",
                ):
                    first.backoffice_service.create_work_item(
                        title="Different export request",
                        context=self._context(),
                        work_type=WorkType.INVOICE_EXPORT,
                        idempotency_key="concurrent-create",
                    )
                with self.assertRaisesRegex(
                    ValueError,
                    "idempotency key is already bound to a different request",
                ):
                    first.backoffice_service.plan_work_item(
                        work_item_id=created[0].id,
                        context=self._context(),
                        planning_input=PlanningInput(
                            requested_outcome="do not export",
                            approved_for_export=False,
                        ),
                        idempotency_key="concurrent-plan",
                    )
            finally:
                first.close()
                second.close()

    def test_backoffice_external_success_requires_reconciliation_after_db_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(self._settings(temp_dir))
            try:
                batch = self._seed_export_batch(container)
                document_id = batch.document_ids[0]
                work_item = container.backoffice_service.create_work_item(
                    title="Export approved invoice",
                    context=self._context(),
                    work_type=WorkType.INVOICE_EXPORT,
                    linked_document_ids=(document_id,),
                )
                plan_result = container.backoffice_service.plan_work_item(
                    work_item_id=work_item.id,
                    context=self._context(),
                    planning_input=PlanningInput(
                        requested_outcome="export invoice",
                        approved_for_export=True,
                    ),
                )
                plan = container.backoffice_plans.get(plan_result.plan_id)
                step = next(
                    item
                    for item in plan.steps
                    if item.action_type == ActionType.EXPORT_APPROVED_INVOICE
                )
                container.backoffice_service.approve_request(
                    approval_id=plan_result.pending_approval_ids[0],
                    context=self._context(),
                )
                original_plan_save = container.backoffice_plans.save
                tool_calls = 0
                original_execute = container.tool_executor.execute

                def count_tool_call(*args, **kwargs):
                    nonlocal tool_calls
                    tool_calls += 1
                    return original_execute(*args, **kwargs)

                def fail_terminal_plan_save(candidate):
                    saved = original_plan_save(candidate)
                    candidate_step = next(item for item in candidate.steps if item.id == step.id)
                    if candidate_step.status == ActionStepStatus.EXECUTED:
                        raise RuntimeError("injected terminal plan failure")
                    return saved

                with (
                    patch.object(
                        container.tool_executor,
                        "execute",
                        side_effect=count_tool_call,
                    ),
                    patch.object(
                        container.backoffice_plans,
                        "save",
                        side_effect=fail_terminal_plan_save,
                    ),
                    self.assertRaisesRegex(
                        RuntimeError,
                        "injected terminal plan failure",
                    ),
                ):
                    container.backoffice_service.execute_approved_step(
                        work_item_id=work_item.id,
                        action_step_id=step.id,
                        context=self._context(),
                    )

                persisted_plan = container.backoffice_plans.get(plan.id)
                persisted_step = next(item for item in persisted_plan.steps if item.id == step.id)
                self.assertEqual(persisted_step.status, ActionStepStatus.EXECUTING)
                persisted_item = container.backoffice_work_items.get(work_item.id)
                self.assertEqual(
                    persisted_item.business_context.get("execution_outcome"),
                    "unknown",
                )
                self.assertEqual(
                    container.documents.get(document_id).status,
                    DocumentStatus.EXPORTED,
                )

                replay = container.backoffice_service.execute_approved_step(
                    work_item_id=work_item.id,
                    action_step_id=step.id,
                    context=self._context(),
                )
                self.assertEqual(replay.status, "blocked")
                self.assertEqual(tool_calls, 1)

                reconciled = container.backoffice_service.reconcile_execution(
                    work_item_id=work_item.id,
                    action_step_id=step.id,
                    context=self._context(),
                    succeeded=True,
                    summary="CSV export was confirmed from the document audit trail.",
                )
                self.assertEqual(reconciled.status, WorkItemStatus.RESOLVED)
                final_plan = container.backoffice_plans.get(plan.id)
                final_step = next(item for item in final_plan.steps if item.id == step.id)
                self.assertEqual(final_step.status, ActionStepStatus.EXECUTED)
                replayed_reconciliation = container.backoffice_service.reconcile_execution(
                    work_item_id=work_item.id,
                    action_step_id=step.id,
                    context=self._context(),
                    succeeded=True,
                    summary="Repeated confirmation.",
                )
                self.assertEqual(
                    replayed_reconciliation.status,
                    WorkItemStatus.RESOLVED,
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "successful reconciliation cannot be overwritten",
                ):
                    container.backoffice_service.reconcile_execution(
                        work_item_id=work_item.id,
                        action_step_id=step.id,
                        context=self._context(),
                        succeeded=False,
                        summary="Conflicting confirmation.",
                    )
            finally:
                container.close()

    def test_active_backoffice_execution_cannot_be_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(self._settings(temp_dir))
            started = threading.Event()
            release = threading.Event()
            responses = []
            errors: list[Exception] = []
            try:
                batch = self._seed_export_batch(container)
                work_item = container.backoffice_service.create_work_item(
                    title="Export approved invoice",
                    context=self._context(),
                    work_type=WorkType.INVOICE_EXPORT,
                    linked_document_ids=(batch.document_ids[0],),
                )
                plan_result = container.backoffice_service.plan_work_item(
                    work_item_id=work_item.id,
                    context=self._context(),
                    planning_input=PlanningInput(
                        requested_outcome="export invoice",
                        approved_for_export=True,
                    ),
                )
                plan = container.backoffice_plans.get(plan_result.plan_id)
                step = next(
                    item
                    for item in plan.steps
                    if item.action_type == ActionType.EXPORT_APPROVED_INVOICE
                )
                container.backoffice_service.approve_request(
                    approval_id=plan_result.pending_approval_ids[0],
                    context=self._context(),
                )
                original_execute = container.tool_executor.execute

                def blocking_execute(*args, **kwargs):
                    started.set()
                    if not release.wait(timeout=5):
                        raise TimeoutError("test tool release timed out")
                    return original_execute(*args, **kwargs)

                def execute() -> None:
                    try:
                        responses.append(
                            container.backoffice_service.execute_approved_step(
                                work_item_id=work_item.id,
                                action_step_id=step.id,
                                context=self._context(),
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                with patch.object(
                    container.tool_executor,
                    "execute",
                    side_effect=blocking_execute,
                ):
                    thread = threading.Thread(target=execute)
                    thread.start()
                    self.assertTrue(started.wait(timeout=5))
                    with self.assertRaisesRegex(
                        ValueError,
                        "active execution cannot be reconciled",
                    ):
                        container.backoffice_service.reconcile_execution(
                            work_item_id=work_item.id,
                            action_step_id=step.id,
                            context=self._context(),
                            succeeded=False,
                            summary="Do not override active work.",
                        )
                    release.set()
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

                self.assertEqual(errors, [])
                self.assertEqual(len(responses), 1)
                self.assertEqual(responses[0].status, "success")
                final_plan = container.backoffice_plans.get(plan.id)
                final_step = next(item for item in final_plan.steps if item.id == step.id)
                self.assertEqual(final_step.status, ActionStepStatus.EXECUTED)
            finally:
                release.set()
                container.close()

    def test_stale_backoffice_execution_can_be_reconciled_after_process_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(self._settings(temp_dir))
            try:
                batch = self._seed_export_batch(container)
                work_item = container.backoffice_service.create_work_item(
                    title="Export approved invoice",
                    context=self._context(),
                    work_type=WorkType.INVOICE_EXPORT,
                    linked_document_ids=(batch.document_ids[0],),
                )
                plan_result = container.backoffice_service.plan_work_item(
                    work_item_id=work_item.id,
                    context=self._context(),
                    planning_input=PlanningInput(
                        requested_outcome="export invoice",
                        approved_for_export=True,
                    ),
                )
                plan = container.backoffice_plans.get(plan_result.plan_id)
                step = next(
                    item
                    for item in plan.steps
                    if item.action_type == ActionType.EXPORT_APPROVED_INVOICE
                )
                container.backoffice_service.approve_request(
                    approval_id=plan_result.pending_approval_ids[0],
                    context=self._context(),
                )
                reservation = container.backoffice_service._reserve_approved_execution(
                    work_item_id=work_item.id,
                    action_step_id=step.id,
                    context=self._context(),
                )
                self.assertTrue(
                    container.backoffice_service._renew_execution_reservation(
                        reservation,
                        self._context(),
                    )
                )
                stale_item = container.backoffice_work_items.get(work_item.id)
                stale_item.attach_context(
                    "execution_heartbeat_at",
                    (datetime.now(UTC) - timedelta(minutes=6)).isoformat(),
                )
                container.backoffice_work_items.save(stale_item)

                reconciled = container.backoffice_service.reconcile_execution(
                    work_item_id=work_item.id,
                    action_step_id=step.id,
                    context=self._context(),
                    succeeded=False,
                    summary="The worker stopped and the accounting system shows no export.",
                )

                self.assertEqual(reconciled.status, WorkItemStatus.FAILED)
                final_plan = container.backoffice_plans.get(plan.id)
                final_step = next(item for item in final_plan.steps if item.id == step.id)
                self.assertEqual(final_step.status, ActionStepStatus.FAILED)
            finally:
                container.close()

    def test_export_start_rolls_back_run_when_batch_transition_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(self._settings(temp_dir))
            try:
                batch = self._seed_export_batch(container)
                original_save = container.export_batches.save_batch

                def fail_running_transition(
                    candidate: ExportBatchRecord,
                ) -> ExportBatchRecord:
                    if candidate.status == ExportBatchStatus.RUNNING:
                        raise RuntimeError("injected batch start failure")
                    return original_save(candidate)

                with (
                    patch.object(
                        container.export_batches,
                        "save_batch",
                        side_effect=fail_running_transition,
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected batch start failure"),
                ):
                    container.export_batch_service.execute(
                        context=self._context(),
                        batch_id=batch.id,
                        idempotency_key="atomic-start",
                    )

                persisted = container.export_batches.get_batch("default", batch.id)
                self.assertIsNotNone(persisted)
                assert persisted is not None
                self.assertEqual(persisted.status, ExportBatchStatus.READY)
                self.assertEqual(container.export_batches.list_runs("default"), [])
            finally:
                container.close()

    def test_export_execution_is_consistent_across_two_sqlite_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            first = build_container(settings)
            second = build_container(settings)
            release_render = threading.Event()
            render_started = threading.Event()
            errors: list[Exception] = []
            completed: list[ExportRunRecord] = []
            try:
                batch = self._seed_export_batch(first)
                original_render = first.export_batch_service.invoice_exports.render_documents_csv

                def blocking_render(documents: list[DocumentRecord]) -> str:
                    render_started.set()
                    if not release_render.wait(timeout=5):
                        raise TimeoutError("Test export render was not released")
                    return original_render(documents)

                def run_first_export() -> None:
                    try:
                        completed.append(
                            first.export_batch_service.execute(
                                context=self._context(),
                                batch_id=batch.id,
                                idempotency_key="shared-key",
                            )
                        )
                    except Exception as exc:
                        errors.append(exc)

                with patch.object(
                    first.export_batch_service.invoice_exports,
                    "render_documents_csv",
                    side_effect=blocking_render,
                ):
                    thread = threading.Thread(target=run_first_export)
                    thread.start()
                    self.assertTrue(render_started.wait(timeout=5))

                    replay = second.export_batch_service.execute(
                        context=self._context(),
                        batch_id=batch.id,
                        idempotency_key="shared-key",
                    )
                    self.assertEqual(replay.status, ExportRunStatus.RUNNING)
                    with self.assertRaises(ExportEligibilityError):
                        second.export_batch_service.execute(
                            context=self._context(),
                            batch_id=batch.id,
                            idempotency_key="different-key",
                        )

                    release_render.set()
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

                persisted_batch = second.export_batches.get_batch("default", batch.id)
                runs = second.export_batches.list_runs("default")
                self.assertEqual(errors, [])
                self.assertEqual(len(completed), 1)
                self.assertEqual(len(runs), 1)
                self.assertEqual(runs[0].status, ExportRunStatus.SUCCEEDED)
                self.assertIsNotNone(persisted_batch)
                assert persisted_batch is not None
                self.assertEqual(persisted_batch.status, ExportBatchStatus.COMPLETED)
                self.assertEqual(persisted_batch.last_run_id, runs[0].id)
            finally:
                release_render.set()
                first.close()
                second.close()

    def test_abandoned_export_run_is_reconciled_before_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(self._settings(temp_dir))
            try:
                batch = self._seed_export_batch(container)
                stale_at = datetime.now(UTC) - timedelta(minutes=15)
                abandoned = ExportRunRecord(
                    workspace_id="default",
                    batch_id=batch.id,
                    document_ids=batch.document_ids,
                    idempotency_key="abandoned-key",
                    destination=batch.destination,
                    export_format=batch.export_format,
                    actor=self._context().actor,
                    created_at=stale_at,
                    updated_at=stale_at,
                )
                container.export_batches.reserve_run(abandoned)
                container.export_batches.save_batch(
                    replace(
                        batch,
                        status=ExportBatchStatus.RUNNING,
                        last_run_id=abandoned.id,
                        updated_at=stale_at,
                    )
                )

                reconciled = container.export_batch_service.execute(
                    context=self._context(),
                    batch_id=batch.id,
                    idempotency_key="abandoned-key",
                )
                persisted_batch = container.export_batches.get_batch("default", batch.id)

                self.assertEqual(reconciled.status, ExportRunStatus.FAILED)
                self.assertEqual(reconciled.error_code, "export_run_abandoned")
                self.assertTrue(reconciled.retryable)
                self.assertIsNotNone(persisted_batch)
                assert persisted_batch is not None
                self.assertEqual(persisted_batch.status, ExportBatchStatus.FAILED)
            finally:
                container.close()

    def test_export_batch_rolls_back_every_document_when_finalization_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            container = build_container(settings)
            try:
                documents = []
                for index in range(2):
                    document = DocumentRecord(
                        original_filename=f"invoice-{index}.pdf",
                        storage_key=f"invoice-{index}.pdf",
                        content_type="application/pdf",
                        status=DocumentStatus.APPROVED,
                    )
                    container.documents.add(document)
                    container.extractions.save(
                        document.id,
                        ExtractionResult(
                            extraction=InvoiceExtraction(
                                data=InvoiceData(
                                    vendor_name=f"Vendor {index}",
                                    invoice_number=f"INV-{index}",
                                    invoice_date=date(2026, 7, 30),
                                    total=Decimal("100.00"),
                                    currency="USD",
                                )
                            ),
                            provider_name="test",
                        ),
                        ValidationReport(issues=()),
                    )
                    documents.append(document)
                batch = ExportBatchRecord(
                    workspace_id="default",
                    document_ids=tuple(document.id for document in documents),
                    destination="csv_download",
                    export_format="csv",
                    created_by="Transaction Test",
                    status=ExportBatchStatus.READY,
                )
                container.export_batches.save_batch(batch)
                original_add = container.documents.add
                write_count = 0

                def fail_second_document_write(document: DocumentRecord) -> DocumentRecord:
                    nonlocal write_count
                    write_count += 1
                    if write_count == 2:
                        raise RuntimeError("injected document finalization failure")
                    return original_add(document)

                with (
                    patch.object(
                        container.documents,
                        "add",
                        side_effect=fail_second_document_write,
                    ),
                    self.assertRaisesRegex(RuntimeError, "Export generation failed"),
                ):
                    container.export_batch_service.execute(
                        context=self._context(),
                        batch_id=batch.id,
                        idempotency_key="transaction-boundary-test",
                    )

                persisted = [container.documents.get(document.id) for document in documents]
                persisted_batch = container.export_batches.get_batch("default", batch.id)
                runs = container.export_batches.list_runs("default")
                self.assertTrue(
                    all(document.status == DocumentStatus.APPROVED for document in persisted)
                )
                self.assertTrue(
                    all(
                        not container.audits.list_for_document(document.id)
                        for document in documents
                    )
                )
                self.assertEqual(persisted_batch.status, ExportBatchStatus.FAILED)
                self.assertEqual(runs[0].status, ExportRunStatus.FAILED)
            finally:
                container.close()

    def test_upload_rolls_back_metadata_and_removes_file_when_job_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            container = build_container(settings)
            try:
                with (
                    patch.object(
                        container.jobs,
                        "add",
                        side_effect=RuntimeError("injected job write failure"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected job write failure"),
                ):
                    container.upload_service.upload_pdf(
                        "invoice.pdf",
                        "application/pdf",
                        [b"%PDF- invoice"],
                        context=self._context(),
                    )

                self.assertEqual(container.documents.list_by_workspace("default"), [])
                self.assertEqual(container.audits.count(), 0)
                self.assertEqual(container.jobs.count(), 0)
                self.assertEqual(list(settings.upload_root.glob("*")), [])
            finally:
                container.close()

    def test_approval_rolls_back_document_and_audit_when_task_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            app = create_app(settings)
            client = TestClient(app)
            try:
                upload = client.post(
                    "/documents/upload",
                    headers=HEADERS,
                    files={
                        "file": (
                            "invoice.pdf",
                            b"%PDF- invoice",
                            "application/pdf",
                        )
                    },
                )
                document_id = UUID(upload.json()["document"]["id"])
                process = client.post(
                    f"/documents/{document_id}/process",
                    headers=HEADERS,
                )
                self.assertEqual(process.json()["document"]["status"], "needs_review")
                events_before = [
                    event.event_type
                    for event in app.state.container.audits.list_for_document(document_id)
                ]

                with (
                    patch.object(
                        app.state.container.reviews,
                        "save",
                        side_effect=RuntimeError("injected review write failure"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected review write failure"),
                ):
                    app.state.container.review_service.approve(
                        document_id,
                        context=self._context(),
                    )

                persisted = app.state.container.documents.get(document_id)
                events_after = [
                    event.event_type
                    for event in app.state.container.audits.list_for_document(document_id)
                ]
                self.assertEqual(persisted.status, DocumentStatus.NEEDS_REVIEW)
                self.assertEqual(events_after, events_before)
            finally:
                app.state.container.close()

    def _settings(self, temp_dir: str) -> Settings:
        root = Path(temp_dir)
        return Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=root / "uploads",
            max_upload_bytes=1_000,
            storage_backend="sqlite",
            sqlite_path=root / "doc_intel.sqlite3",
        )

    def _context(self) -> SecurityContext:
        return SecurityContext(
            actor="Transaction Test",
            is_admin=True,
            workspace_id="default",
            user_id="transaction-test",
            role="admin",
        )

    def _seed_export_batch(self, container: AppContainer) -> ExportBatchRecord:
        document = DocumentRecord(
            original_filename="invoice.pdf",
            storage_key="invoice.pdf",
            content_type="application/pdf",
            status=DocumentStatus.APPROVED,
        )
        container.documents.add(document)
        container.extractions.save(
            document.id,
            ExtractionResult(
                extraction=InvoiceExtraction(
                    data=InvoiceData(
                        vendor_name="Acme Logistics",
                        invoice_number="INV-ATOMIC",
                        invoice_date=date(2026, 7, 30),
                        total=Decimal("100.00"),
                        currency="USD",
                    )
                ),
                provider_name="test",
            ),
            ValidationReport(issues=()),
        )
        batch = ExportBatchRecord(
            workspace_id="default",
            document_ids=(document.id,),
            destination="csv_download",
            export_format="csv",
            created_by=self._context().actor,
            status=ExportBatchStatus.READY,
        )
        container.export_batches.save_batch(batch)
        return batch


if __name__ == "__main__":
    unittest.main()
