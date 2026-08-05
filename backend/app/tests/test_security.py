from __future__ import annotations

import unittest

from app.core.security import SecurityContext, SessionStore, UnauthorizedError, authenticate_access_token, require_role
from app.core.settings import Settings


class SecurityTests(unittest.TestCase):
    def test_tokens_map_to_server_owned_identity(self) -> None:
        settings = Settings(admin_token="admin-secret", uploader_token="upload-secret", reviewer_token="review-secret", workspace_id="acme")
        context = authenticate_access_token("review-secret", settings)
        self.assertEqual((context.user_id, context.role, context.workspace_id), ("reviewer", "reviewer", "acme"))

    def test_caller_cannot_supply_identity_to_authenticator(self) -> None:
        with self.assertRaises(UnauthorizedError):
            authenticate_access_token("forged", Settings(admin_token="admin-secret"))

    def test_session_is_opaque_and_revocable(self) -> None:
        store = SessionStore(60)
        context = SecurityContext("Operator", "operator", "uploader", "alpha")
        session_id = store.create(context)
        self.assertNotIn("operator", session_id)
        self.assertEqual(store.get(session_id), context)
        store.revoke(session_id)
        self.assertIsNone(store.get(session_id))

    def test_role_boundary_is_explicit(self) -> None:
        with self.assertRaises(UnauthorizedError):
            require_role(SecurityContext("Reviewer", "reviewer", "reviewer", "alpha"), "admin")


if __name__ == "__main__":
    unittest.main()
