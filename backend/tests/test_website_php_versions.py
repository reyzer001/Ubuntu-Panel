import tempfile
import unittest

from app.services import collectors


class PhpVersionSupportTest(unittest.TestCase):
    def test_supported_php_versions_include_legacy_and_latest(self):
        self.assertIn("7.0", collectors.SUPPORTED_PHP_VERSIONS)
        self.assertEqual(collectors.SUPPORTED_PHP_VERSIONS[0], "7.0")
        self.assertEqual(collectors.SUPPORTED_PHP_VERSIONS[-1], "8.5")

    def test_normalize_php_version_accepts_7_0_and_latest(self):
        self.assertEqual(collectors.normalize_php_version("7.0"), "7.0")
        self.assertEqual(collectors.normalize_php_version("8.5"), "8.5")

    def test_detect_project_php_version_handles_legacy_pattern(self):
        project = tempfile.mkdtemp()
        with open(f"{project}/composer.json", "w", encoding="utf-8") as fh:
            fh.write('{"require": {"php": "^7.0"}}')
        self.assertEqual(collectors._detect_php_version(project), "7.0")


if __name__ == "__main__":
    unittest.main()
