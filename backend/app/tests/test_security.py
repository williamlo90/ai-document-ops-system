from __future__ import annotations

import unittest
from pathlib import Path

from app.core.security import (
    SecurityContext,
    UnauthorizedError,
    authenticate_access_token,
    require_admin,
    require_any_role,
    validate_access_token_policy,
)
from app.core.settings import Settings


class SecurityTests(unittest.TestCase):
    def test_admin_access_token_maps_to_server_owned_identity(self) -> None:
        context = authenticate_access_token(
            "secret",
            Settings(
                app_env="test",
                admin_token="secret",
                upload_root=Path("uploads"),
                max_upload_bytes=1000,
            ),
        )

        self.assertEqual(context, SecurityContext(actor="Administrator", is_admin=True))

    def test_access_token_maps_to_server_owned_reviewer_identity(self) -> None:
        context = authenticate_access_token(
            "review-secret",
            Settings(
                app_env="test",
                admin_token="admin-secret",
                uploader_token="upload-secret",
                reviewer_token="review-secret",
                workspace_id="acme",
                upload_root=Path("uploads"),
                max_upload_bytes=1000,
            ),
        )

        self.assertEqual(context.workspace_id, "acme")
        self.assertEqual(context.user_id, "reviewer")
        self.assertEqual(context.actor, "Invoice Reviewer")
        self.assertEqual(context.role, "reviewer")
        self.assertFalse(context.is_admin)

    def test_access_token_rejects_missing_or_wrong_token(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token="secret",
            upload_root=Path("uploads"),
            max_upload_bytes=1000,
        )
        with self.assertRaises(UnauthorizedError):
            authenticate_access_token(None, settings)
        with self.assertRaises(UnauthorizedError):
            authenticate_access_token("wrong", settings)

    def test_duplicate_role_tokens_are_rejected(self) -> None:
        settings = Settings(
            app_env="local",
            admin_token="same-token",
            uploader_token="same-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1000,
        )

        with self.assertRaises(ValueError):
            validate_access_token_policy(settings)

    def test_require_admin_rejects_non_admin_context(self) -> None:
        with self.assertRaises(UnauthorizedError):
            require_admin(SecurityContext(actor="viewer", is_admin=False))

    def test_require_any_role_rejects_fake_admin_role_without_admin_access(self) -> None:
        with self.assertRaises(UnauthorizedError):
            require_any_role(
                SecurityContext(actor="viewer", is_admin=False),
                {"admin", "reviewer"},
            )

    def test_require_any_role_allows_reviewer_role(self) -> None:
        require_any_role(
            SecurityContext(actor="reviewer", is_admin=False, role="reviewer"),
            {"admin", "reviewer"},
        )


if __name__ == "__main__":
    unittest.main()
