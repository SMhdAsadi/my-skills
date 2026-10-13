import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = HERE.parent / "assets" / "walkthrough-template.html"


class TestWalkthroughTemplate(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TEMPLATE_PATH.exists(), "Template file must exist")
        self.content = TEMPLATE_PATH.read_text(encoding="utf-8")

    def test_template_size_is_lean(self):
        # The template must be under 25 KB (previously ~93 KB due to base64 font)
        size_kb = len(self.content.encode("utf-8")) / 1024
        self.assertLess(
            size_kb,
            25,
            f"Template size is {size_kb:.1f} KB, expected < 25 KB without base64 bloat",
        )

    def test_no_embedded_base64_fonts(self):
        self.assertNotIn(";base64,d09GMgABAAAA", self.content)
        self.assertNotIn("data:font/woff2;base64", self.content)

    def test_local_vazirmatn_font_stack(self):
        self.assertIn('local("Vazirmatn")', self.content)
        self.assertIn('local("Vazir")', self.content)

    def test_editor_schemes_supported(self):
        # Must support zed, idea (JetBrains), android-studio, and goland alongside VS Code variants
        for ed in ["vscode", "cursor", "windsurf", "zed", "android-studio", "goland", "idea", "copy"]:
            self.assertIn(ed, self.content)
        self.assertIn("Android Studio", self.content)
        self.assertIn("GoLand", self.content)

    def test_copy_button_and_clipboard_support(self):
        self.assertIn("clipboard.writeText", self.content)
        self.assertIn("cp-btn", self.content)

    def test_form_inputs_not_trapped_by_keydown(self):
        # Must ignore INPUT elements in keydown listener
        self.assertIn("INPUT", self.content)

    def test_rtl_branch_arrow_direction(self):
        # Branch arrow must be direction-aware: points left in RTL, right in LTR
        self.assertIn("R?'←':'→'", self.content)

    def test_rtl_rich_arrow_normalization(self):
        # rich() must normalize rightwards progression arrows to leftwards in RTL
        self.assertIn("replace(/[→➔➜]|->/g,'←')", self.content)

    def test_test_step_checkboxes_and_persistence(self):
        # Test step must use checkboxes with review-walkthrough-test localStorage key
        self.assertIn("review-walkthrough-test:", self.content)
        self.assertIn("id:'t'+i", self.content)


if __name__ == "__main__":
    unittest.main()
