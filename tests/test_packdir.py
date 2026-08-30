"""Tests for packdir. Stdlib unittest only. No network."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("packdir", ROOT / "packdir.py")
pd = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["packdir"] = pd
SPEC.loader.exec_module(pd)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class GitignoreTests(unittest.TestCase):
    def _rules(self, tmp: Path, rel_gi: str, body: str):
        gi = _write(tmp / rel_gi, body)
        return pd.load_gitignore(gi, tmp)

    def test_root_unanchored(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "*.log\n")
            _write(tmp / "a.log", "x")
            _write(tmp / "keep.txt", "y")
            _write(tmp / "sub" / "b.log", "z")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("a.log", rels)
            self.assertNotIn("sub/b.log", rels)
            self.assertIn("keep.txt", rels)

    def test_nested_does_not_affect_sibling(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "a" / ".gitignore", "*.log\n")
            _write(tmp / "a" / "x.log", "no")
            _write(tmp / "a" / "ok.txt", "yes")
            _write(tmp / "b" / "x.log", "keep")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("a/x.log", rels)
            self.assertIn("b/x.log", rels)
            self.assertIn("a/ok.txt", rels)

    def test_negation_last_wins(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "*.tmp\n!keep.tmp\n")
            _write(tmp / "drop.tmp", "1")
            _write(tmp / "keep.tmp", "2")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("drop.tmp", rels)
            self.assertIn("keep.tmp", rels)

    def test_directory_only(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "build/\n")
            _write(tmp / "build" / "out.txt", "x")
            _write(tmp / "buildfile", "keep")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("build/out.txt", rels)
            self.assertIn("buildfile", rels)

    def test_anchored_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "/onlyroot.log\n")
            _write(tmp / "onlyroot.log", "no")
            _write(tmp / "sub" / "onlyroot.log", "yes")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("onlyroot.log", rels)
            self.assertIn("sub/onlyroot.log", rels)

    def test_escaped_hash_and_bang(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "\\#hashfile\n\\!bangfile\n")
            _write(tmp / "#hashfile", "x")
            _write(tmp / "!bangfile", "y")
            _write(tmp / "ok.txt", "z")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertNotIn("#hashfile", rels)
            self.assertNotIn("!bangfile", rels)
            self.assertIn("ok.txt", rels)

    def test_comment_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".gitignore", "# *.log\n")
            _write(tmp / "a.log", "x")
            files = pd.collect_files(tmp, use_gitignore=True, include=[], exclude=[])
            rels = {p.relative_to(tmp).as_posix() for p in files}
            self.assertIn("a.log", rels)


class SecretTests(unittest.TestCase):
    def test_env_omitted_example_kept(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".env", "SECRET=1")
            _write(tmp / ".env.local", "SECRET=2")
            _write(tmp / ".env.example", "SECRET=")
            _write(tmp / ".env.sample", "SECRET=")
            _write(tmp / ".env.template", "SECRET=")
            _write(tmp / "app.py", "print(1)\n")
            packed = [
                pd.read_packed(tmp, p, include_secrets=False)
                for p in pd.collect_files(tmp, use_gitignore=False, include=[], exclude=[])
            ]
            kinds = {p.rel: p.kind for p in packed}
            self.assertEqual(kinds[".env"], "secret")
            self.assertEqual(kinds[".env.local"], "secret")
            self.assertEqual(kinds[".env.example"], "text")
            self.assertEqual(kinds[".env.sample"], "text")
            self.assertEqual(kinds[".env.template"], "text")

    def test_private_key_filename(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "id_rsa", "fake")
            _write(tmp / "cert.pem", "fake")
            packed = pd.read_packed(tmp, tmp / "id_rsa", include_secrets=False)
            self.assertEqual(packed.kind, "secret")
            packed = pd.read_packed(tmp, tmp / "cert.pem", include_secrets=False)
            self.assertEqual(packed.kind, "secret")

    def test_include_secrets_override(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / ".env", "SECRET=1")
            packed = pd.read_packed(tmp, tmp / ".env", include_secrets=True)
            self.assertEqual(packed.kind, "text")

    def test_content_scan_omits(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "notes.txt", "key = AKIA" + "IOSFODNN7EXAMPLE\n")
            packed = pd.read_packed(tmp, tmp / "notes.txt", include_secrets=False)
            self.assertEqual(packed.kind, "suspicious")

    def test_cli_include_secrets_warns(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "ok.py", "x=1\n")
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                code = pd.main([str(tmp), "--include-secrets"])
            finally:
                sys.stderr = old
            self.assertEqual(code, 0)
            self.assertIn("WARNING: --include-secrets", buf.getvalue())


class TreeAndOutputTests(unittest.TestCase):
    def test_tree_shows_directories(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "src" / "main.py", "a=1\n")
            _write(tmp / "tests" / "main.py", "b=2\n")
            lines = pd.tree_lines(tmp, ["src/main.py", "tests/main.py"])
            text = "\n".join(lines)
            self.assertIn("src/", text)
            self.assertIn("tests/", text)
            self.assertEqual(text.count("main.py"), 2)
            src_i = lines.index("  src/")
            test_i = lines.index("  tests/")
            self.assertEqual(lines[src_i + 1].strip(), "main.py")
            self.assertEqual(lines[test_i + 1].strip(), "main.py")

    def test_output_inside_dir_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "a.py", "print(1)\n")
            out = tmp / "prompt.md"
            out.write_text("OLD PACK\n", encoding="utf-8")
            code = pd.main([str(tmp), "-o", str(out)])
            self.assertEqual(code, 0)
            body = out.read_text(encoding="utf-8")
            self.assertNotIn("OLD PACK", body)
            self.assertNotIn("### prompt.md", body)
            # second run still excludes itself
            code = pd.main([str(tmp), "-o", str(out)])
            self.assertEqual(code, 0)
            body2 = out.read_text(encoding="utf-8")
            self.assertNotIn("### prompt.md", body2)
            self.assertIn("### a.py", body2)

    def test_fence_longer_than_backticks(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "doc.md", "use ````fence```` here\n")
            packed = pd.read_packed(tmp, tmp / "doc.md", include_secrets=False)
            self.assertTrue(packed.body.startswith("`````"))

    def test_utf8_byte_count(self):
        text = "café"  # é is 2 bytes in utf-8
        self.assertEqual(len(text), 4)
        self.assertEqual(len(text.encode("utf-8")), 5)
        tokens = pd.estimate_tokens(text)
        self.assertEqual(tokens, (5 + 3) // 4)

    def test_size_before_read_oversized(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            big = tmp / "big.txt"
            big.write_bytes(b"x" * (pd.MAX_FILE_BYTES + 10))
            packed = pd.read_packed(tmp, big, include_secrets=False)
            self.assertEqual(packed.kind, "oversized")

    def test_binary_sniff_nul(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            p = tmp / "data.dat"
            p.write_bytes(b"hello\x00world")
            packed = pd.read_packed(tmp, p, include_secrets=False)
            self.assertEqual(packed.kind, "binary")


class BudgetTests(unittest.TestCase):
    def _pack_text(self, rel: str, body: str) -> "pd.PackedFile":
        fence = pd.fence_for(body)
        return pd.PackedFile(rel, f"{fence}\n{body}\n{fence}", "text", raw=body)

    def test_largest_drops_biggest_first(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            files = [
                self._pack_text("README.md", "R" * 200),
                self._pack_text("vendor/big.js", "V" * 4000),
                self._pack_text("src/app.py", "S" * 200),
            ]
            kept, dropped, md = pd.apply_budget(tmp, files, budget=200, policy="largest")
            self.assertTrue(any(x.startswith("vendor/big.js") for x in dropped))
            self.assertIn("largest", dropped[0])

    def test_smart_drops_vendor_before_source(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            vendor = self._pack_text("vendor/lib.js", "V" * 400)
            src = self._pack_text("src/app.py", "S" * 40)
            readme = self._pack_text("README.md", "R" * 40)
            kept, dropped, md = pd.apply_budget(
                tmp, [vendor, src, readme], budget=120, policy="smart"
            )
            names = [k.rel for k in kept]
            self.assertTrue(any("vendor/lib.js" in x for x in dropped))
            self.assertIn("README.md", names)

    def test_smart_does_not_drop_all_source_for_one_large(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            huge = self._pack_text("src/huge.py", "H" * 5000)
            small1 = self._pack_text("src/a.py", "print(1)\n")
            small2 = self._pack_text("src/b.py", "print(2)\n")
            kept, dropped, md = pd.apply_budget(
                tmp, [huge, small1, small2], budget=80, policy="smart"
            )
            kept_rels = {k.rel for k in kept}
            self.assertTrue(any("src/huge.py" in x for x in dropped))
            self.assertTrue({"src/a.py", "src/b.py"} & kept_rels)

    def test_dropped_line_has_tokens_and_reason(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            files = [
                self._pack_text("a.py", "A" * 100),
                self._pack_text("b.py", "B" * 4000),
            ]
            kept, dropped, md = pd.apply_budget(tmp, files, budget=50, policy="largest")
            self.assertTrue(dropped)
            self.assertIn("tokens", dropped[0])
            self.assertIn("largest", dropped[0])

    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            files = [
                self._pack_text("z.py", "Z" * 1000),
                self._pack_text("a.py", "A" * 1000),
            ]
            k1, d1, _ = pd.apply_budget(tmp, files, budget=80, policy="largest")
            k2, d2, _ = pd.apply_budget(tmp, files, budget=80, policy="largest")
            self.assertEqual(d1, d2)
            self.assertEqual([x.rel for x in k1], [x.rel for x in k2])


def _run_main(argv):
    out = io.StringIO()
    err = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = pd.main(argv)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    return code, out.getvalue(), err.getvalue()


class CleanPackTests(unittest.TestCase):
    def test_skipped_files_absent_from_pack_body(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "app.py", "print(1)\n")
            _write(tmp / ".env", "SECRET=1\n")
            (tmp / "blob.bin").write_bytes(b"hello\x00world")
            big = tmp / "huge.txt"
            big.write_bytes(b"x" * (pd.MAX_FILE_BYTES + 10))
            code, stdout, stderr = _run_main([str(tmp)])
            self.assertEqual(code, 0)
            self.assertIn("### app.py", stdout)
            self.assertIn("print(1)", stdout)
            self.assertNotIn("### .env", stdout)
            self.assertNotIn("_secret filename omitted_", stdout)
            self.assertNotIn("### blob.bin", stdout)
            self.assertNotIn("_binary skipped_", stdout)
            self.assertNotIn("### huge.txt", stdout)
            self.assertNotIn("_skipped,", stdout)
            self.assertIn("omitted secret filename: .env", stderr)
            self.assertIn("binaries skipped", stderr)
            self.assertIn("oversized skipped", stderr)

    def test_budget_holds_when_binaries_exist(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "app.py", "print('ok')\n")
            (tmp / "photo.png").write_bytes(b"\x89PNG\x00" + b"x" * 200)
            (tmp / "data.bin").write_bytes(b"abc\x00def")
            _write(tmp / ".env", "SECRET=nope\n")
            text_only = pd.read_packed(tmp, tmp / "app.py", include_secrets=False)
            budget = pd.estimate_tokens(pd.render(tmp, [text_only], []))
            code, stdout, stderr = _run_main([str(tmp), "--budget", str(budget)])
            self.assertEqual(code, 0)
            self.assertLessEqual(pd.estimate_tokens(stdout), budget)
            self.assertNotIn("_binary skipped_", stdout)
            self.assertNotIn("### photo.png", stdout)
            self.assertNotIn("### data.bin", stdout)
            self.assertNotIn("### .env", stdout)
            self.assertIn("binaries skipped", stderr)

    def test_tight_budget_stays_at_or_under_limit(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "app.py", "print('ok')\n")
            (tmp / "photo.png").write_bytes(b"\x89PNG\x00" + b"x" * 200)
            _write(tmp / ".env", "SECRET=nope\n")
            code, stdout, stderr = _run_main([str(tmp), "--budget", "20"])
            self.assertEqual(code, 0)
            self.assertLessEqual(pd.estimate_tokens(stdout), 20)
            self.assertNotIn("_binary skipped_", stdout)
            self.assertNotIn("### photo.png", stdout)
            self.assertNotIn("### .env", stdout)
            self.assertIn("dropped to fit budget", stderr)


class ListTests(unittest.TestCase):
    def test_list_prints_paths_not_markdown_pack(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "src" / "app.py", "print(1)\n")
            _write(tmp / "README.md", "hello\n")
            (tmp / "blob.bin").write_bytes(b"\x00\x01")
            code, stdout, stderr = _run_main([str(tmp), "--list"])
            self.assertEqual(code, 0)
            self.assertIn("src/app.py", stdout)
            self.assertIn("README.md", stdout)
            self.assertIn("~", stdout)
            self.assertNotIn("## Tree", stdout)
            self.assertNotIn("## Files", stdout)
            self.assertNotIn("### src/app.py", stdout)
            self.assertNotIn("Packed for an LLM prompt", stdout)
            self.assertNotIn("blob.bin", stdout)
            self.assertIn("considered", stderr)
            self.assertIn("text packed", stderr)

    def test_list_with_budget_shows_drops(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "keep.py", "x=1\n")
            _write(tmp / "vendor" / "big.js", "V" * 4000)
            code, stdout, stderr = _run_main(
                [str(tmp), "--list", "--budget", "80", "--budget-policy", "largest"]
            )
            self.assertEqual(code, 0)
            self.assertIn("keep.py", stdout)
            self.assertIn("dropped to fit budget", stdout)
            self.assertIn("vendor/big.js", stdout)
            self.assertIn("dropped to fit budget", stderr)
            self.assertNotIn("## Files", stdout)
            self.assertNotIn("### keep.py", stdout)


class FormatTests(unittest.TestCase):
    def test_format_xml_includes_paths_and_contents(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "src" / "app.py", "print(1)\n")
            _write(tmp / "README.md", "hello pack\n")
            (tmp / "blob.bin").write_bytes(b"\x00bin")
            code, stdout, stderr = _run_main([str(tmp), "--format", "xml"])
            self.assertEqual(code, 0)
            self.assertIn("<documents>", stdout)
            self.assertIn("</documents>", stdout)
            self.assertIn('path="src/app.py"', stdout)
            self.assertIn("print(1)", stdout)
            self.assertIn('path="README.md"', stdout)
            self.assertIn("hello pack", stdout)
            self.assertNotIn("blob.bin", stdout)
            self.assertNotIn("_binary skipped_", stdout)
            self.assertIn("considered", stderr)

    def test_format_markdown_still_uses_headings(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp / "a.py", "x=1\n")
            code, stdout, _stderr = _run_main([str(tmp), "--format", "markdown"])
            self.assertEqual(code, 0)
            self.assertIn("### a.py", stdout)
            self.assertIn("```", stdout)


class VersionTests(unittest.TestCase):
    def test_version_prints_version(self):
        out = io.StringIO()
        err = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            with self.assertRaises(SystemExit) as cm:
                pd.main(["--version"])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(pd.VERSION, out.getvalue())
        self.assertIn("packdir", out.getvalue())


if __name__ == "__main__":
    unittest.main()
