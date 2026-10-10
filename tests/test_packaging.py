from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagingConfigurationTests(unittest.TestCase):
    def test_runtime_exclusions_are_root_anchored(self):
        source = (ROOT / "packaging/yunyoubao.iss").read_text(encoding="utf-8")
        patterns = re.search(r'Excludes:\s*"([^"]+)"', source).group(1).split(",")
        for pattern in patterns:
            if "\\" in pattern:
                self.assertTrue(pattern.startswith("\\"), pattern)
        self.assertNotIn("runtime\\*", patterns)
        self.assertNotIn("*runtime*", patterns)

    def test_directory_selection_and_chinese_notices(self):
        source = (ROOT / "packaging/yunyoubao.iss").read_text(encoding="utf-8")
        self.assertIn("DisableDirPage=no", source)
        self.assertIn("PrivilegesRequired=lowest", source)
        self.assertIn("UsePreviousAppDir=yes", source)
        for key in ("LicenseFile", "InfoBeforeFile"):
            filename = re.search(rf"^{key}=(.+)$", source, re.MULTILINE).group(1).strip()
            text = (ROOT / "packaging" / filename).read_text(encoding="utf-8")
            for word in ("GPL", "授权", "垃圾", "用户数据"):
                self.assertIn(word, text)
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (ROOT / "LICENSE").read_text())

    def test_application_and_project_versions_match(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        version = re.search(r'^VERSION = "([^"]+)"',
                            (ROOT / "main.py").read_text(encoding="utf-8"), re.MULTILINE).group(1)
        self.assertEqual(project["project"]["version"], version)


if __name__ == "__main__":
    unittest.main()
