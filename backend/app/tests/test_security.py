from __future__ import annotations

import unittest

from app.core.security import (
    SecurityContext,
    UnauthorizedError,
    require_admin,
    require_any_role,
    verify_admin_token,
)


class SecurityTests(unittest.TestCase):
    def test_verify_admin_token_accepts_matching_token(self) -> None:
        context = verify_admin_token("secret", "secret")

        self.assertEqual(context, SecurityContext(actor="admin", is_admin=True))

    def test_verify_admin_token_accepts_workspace_user_and_role(self) -> None:
        context = verify_admin_token(
            "secret",
            "secret",
            workspace_id="acme",
            user_id="reviewer-1",
            role="reviewer",
        )

        self.assertEqual(context.workspace_id, "acme")
        self.assertEqual(context.user_id, "reviewer-1")
        self.assertEqual(context.actor, "reviewer-1")
        self.assertEqual(context.role, "reviewer")
        self.assertFalse(context.is_admin)

    def test_verify_admin_token_rejects_missing_or_wrong_token(self) -> None:
        with self.assertRaises(UnauthorizedError):
            verify_admin_token(None, "secret")
        with self.assertRaises(UnauthorizedError):
            verify_admin_token("wrong", "secret")

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
