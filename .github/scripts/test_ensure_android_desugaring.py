import tempfile
import unittest
from pathlib import Path

from ensure_android_desugaring import DEPENDENCY, FLAG, ensure_desugaring


class EnsureDesugaringTests(unittest.TestCase):
    def test_creates_missing_compile_options_and_dependencies(self):
        source = """plugins { id("com.android.application") }
android {
    namespace = "example"
    defaultConfig { minSdk = 26 }
}
"""
        result = ensure_desugaring(source)
        self.assertIn(FLAG, result)
        self.assertIn(DEPENDENCY, result)
        self.assertIn("minSdk = 26", result)

    def test_merges_existing_blocks_without_duplicates(self):
        source = """plugins { id("com.android.application") }
android {
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
    }
}
dependencies {
    implementation("example:lib:1.0")
}
"""
        once = ensure_desugaring(source)
        twice = ensure_desugaring(once)
        self.assertEqual(once, twice)
        self.assertEqual(1, once.count(FLAG))
        self.assertEqual(1, once.count(DEPENDENCY))
        self.assertIn('implementation("example:lib:1.0")', once)

    def test_rejects_missing_android_block(self):
        with self.assertRaisesRegex(ValueError, "android block is missing"):
            ensure_desugaring("plugins { id(\"x\") }")


if __name__ == "__main__":
    unittest.main()
