#!/usr/bin/env python3
"""Idempotently configure core-library desugaring in Flutter's generated Kotlin DSL."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

FLAG = "isCoreLibraryDesugaringEnabled = true"
DEPENDENCY = 'coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")'


def find_block(source: str, name: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
    """Return opening/closing brace positions for a named Kotlin DSL block.

    Braces inside comments and quoted strings are ignored. Returned positions
    refer to the original source, so callers can safely insert before the close.
    """
    if end is None:
        end = len(source)
    declaration = re.compile(r"(?m)^\s*" + re.escape(name) + r"\s*\{")
    match = declaration.search(source, start, end)
    if match is None:
        return None

    opening = source.find("{", match.start(), match.end())
    depth = 0
    i = opening
    state = "code"
    quote = ""
    while i < end:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < end else ""

        if state == "line_comment":
            if ch == "\n":
                state = "code"
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 1
        elif state == "string":
            if ch == "\\":
                i += 1
            elif ch == quote:
                state = "code"
        else:
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif ch in ('"', "'"):
                state = "string"
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return opening, i
        i += 1
    raise ValueError(f"Unclosed {name} block")


def insert_into_block(source: str, name: str, addition: str, *, start: int = 0, end: int | None = None) -> str:
    block = find_block(source, name, start, end)
    if block is None:
        raise ValueError(f"{name} block is missing")
    opening, closing = block
    # Preserve the existing closing brace and insert content immediately before it.
    return source[:closing] + addition + source[closing:]


def ensure_desugaring(source: str) -> str:
    android = find_block(source, "android")
    if android is None:
        raise ValueError("android block is missing")
    android_open, android_close = android

    # Only look for compileOptions inside android { ... }.
    compile_options = find_block(source, "compileOptions", android_open + 1, android_close)
    if compile_options is None:
        source = insert_into_block(
            source, "android",
            "\n    compileOptions {\n"
            "        sourceCompatibility = JavaVersion.VERSION_17\n"
            "        targetCompatibility = JavaVersion.VERSION_17\n"
            f"        {FLAG}\n"
            "    }\n",
        )
    elif FLAG not in source[compile_options[0]:compile_options[1]]:
        source = insert_into_block(source, "compileOptions", f"\n        {FLAG}\n")

    # Recompute after any insertion. A top-level dependencies block is preferred.
    dependencies = find_block(source, "dependencies")
    if dependencies is None:
        source = source.rstrip() + (
            "\n\ndependencies {\n"
            f"    {DEPENDENCY}\n"
            "}\n"
        )
    elif DEPENDENCY not in source[dependencies[0]:dependencies[1]]:
        source = insert_into_block(source, "dependencies", f"\n    {DEPENDENCY}\n")

    # Verify exactly the required declarations exist in the intended blocks.
    android = find_block(source, "android")
    assert android is not None
    compile_options = find_block(source, "compileOptions", android[0] + 1, android[1])
    dependencies = find_block(source, "dependencies")
    if compile_options is None or FLAG not in source[compile_options[0]:compile_options[1]]:
        raise ValueError("Desugaring flag is not inside android.compileOptions")
    if dependencies is None or DEPENDENCY not in source[dependencies[0]:dependencies[1]]:
        raise ValueError("Desugaring dependency is not inside dependencies")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("flutter_app/android/app/build.gradle.kts"),
        help="generated Kotlin Gradle file (default: Flutter app Gradle file)",
    )
    args = parser.parse_args()
    if not args.file.is_file():
        raise SystemExit(f"Generated Gradle file not found: {args.file}")
    original = args.file.read_text(encoding="utf-8")
    try:
        updated = ensure_desugaring(original)
    except ValueError as exc:
        raise SystemExit(f"Gradle patch failed: {exc}") from exc
    args.file.write_text(updated, encoding="utf-8")
    # Idempotency check: a second pass must not change the file.
    if ensure_desugaring(args.file.read_text(encoding="utf-8")) != args.file.read_text(encoding="utf-8"):
        raise SystemExit("Gradle patch is not idempotent")
    print(f"Android core-library desugaring configured: {args.file}")


if __name__ == "__main__":
    main()
