import unittest

from app.providers.factory import build_extractor


class ProviderFactoryTests(unittest.TestCase):
    def test_mock_path_requires_no_credential(self) -> None:
        self.assertEqual(build_extractor("mock").name, "mock")
        with self.assertRaises(ValueError):
            build_extractor("unknown")
