"""Regression tests for the generated Android Kotlin Gradle desugaring patch."""
import unittest

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
        self.assertEqual(1, result.count(FLAG))
        self.assertEqual(1, result.count(DEPENDENCY))

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

    def test_adds_only_missing_dependency_when_compile_option_exists(self):
        source = """plugins { id("com.android.application") }
android {
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }
}
dependencies {
    implementation("example:lib:1.0")
}
"""
        result = ensure_desugaring(source)
        self.assertEqual(1, result.count(FLAG))
        self.assertEqual(1, result.count(DEPENDENCY))
        self.assertIn('implementation("example:lib:1.0")', result)

    def test_braces_inside_comments_and_strings_do_not_end_blocks(self):
        source = '''plugins { id("com.android.application") }
android {
    namespace = "example"
    // A closing brace in a comment: }
    val sample = "brace } remains inside this string"
    defaultConfig { minSdk = 26 }
}
'''
        result = ensure_desugaring(source)
        self.assertIn("defaultConfig { minSdk = 26 }", result)
        self.assertIn(FLAG, result)
        self.assertIn(DEPENDENCY, result)
        self.assertEqual(result, ensure_desugaring(result))

    def test_rejects_missing_android_block(self):
        with self.assertRaisesRegex(ValueError, "android block is missing"):
            ensure_desugaring('plugins { id("x") }')

    def test_does_not_accept_compile_options_outside_android(self):
        source = '''plugins { id("com.android.application") }
compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
}
android {
    namespace = "example"
}
'''
        result = ensure_desugaring(source)
        android_open = result.index("android {")
        android_close = result.index("\n}", android_open)
        android_section = result[android_open:android_close]
        self.assertIn("compileOptions {", android_section)
        self.assertIn(FLAG, android_section)


if __name__ == "__main__":
    unittest.main()
