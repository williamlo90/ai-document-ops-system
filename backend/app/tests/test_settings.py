from __future__ import annotations

import unittest

from app.core.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_require_no_personal_configuration(self) -> None:
        self.assertEqual(Settings.from_environment({}), Settings())

    def test_environment_values_are_explicitly_parsed(self) -> None:
        settings = Settings.from_environment(
            {"APP_ENV": "test", "DATABASE_READY": "false", "STORAGE_READY": "yes"}
        )

        self.assertEqual(settings.environment, "test")
        self.assertFalse(settings.database_ready)
        self.assertTrue(settings.storage_ready)

    def test_invalid_boolean_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "DATABASE_READY must be a boolean value"):
            Settings.from_environment({"DATABASE_READY": "perhaps"})


if __name__ == "__main__":
    unittest.main()
