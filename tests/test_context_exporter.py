"""Unit tests for Eagles Wing ML Context Exporter.

Tests all security, discovery, sanitization, size limits, and exclusion requirements
using isolated temporary directories (fixtures) to protect real application assets.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORTER_PATH = PROJECT_ROOT / "tools" / "context_exporter.py"
LAUNCHER_PATH = PROJECT_ROOT / "export-project-context.zsh"

import sys
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from context_exporter import ContextExporter, MAX_REPORT_SIZE, MAX_SOURCE_FILE_SIZE


class TestContextExporter(unittest.TestCase):
    """Test suite covering the 17 core requirements from the Master Prompt."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.fixture_root = Path(self.temp_dir.name)

        # Build a safe mock project structure
        (self.fixture_root / "build_index.py").write_text(
            'MODEL = "sentence-transformers/all-MiniLM-L6-v2"\nprint("building index")\n',
            encoding="utf-8"
        )
        (self.fixture_root / "engine.py").write_text(
            'def recommend(text, top_k=5):\n    return {"recommendations": []}\n',
            encoding="utf-8"
        )
        (self.fixture_root / "server.py").write_text(
            'from starlette.routing import Route\nroutes = [Route("/health", lambda r: None)]\n',
            encoding="utf-8"
        )
        (self.fixture_root / "ui.py").write_text(
            'import streamlit as st\nst.title("Test UI")\n',
            encoding="utf-8"
        )
        (self.fixture_root / "requirements.txt").write_text(
            'streamlit>=1.58\nnumpy>=1.26\n',
            encoding="utf-8"
        )
        (self.fixture_root / "README.md").write_text(
            '# Test Project\nProject description\n',
            encoding="utf-8"
        )
        (self.fixture_root / ".gitignore").write_text(
            '.venv/\nartifacts/\n',
            encoding="utf-8"
        )
        tools_dir = self.fixture_root / "tools"
        tools_dir.mkdir()
        shutil.copy(EXPORTER_PATH, tools_dir / "context_exporter.py")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_run_from_project_root_succeeds(self):
        """1. Running from the project root succeeds."""
        cmd = [sys.executable, str(self.fixture_root / "tools" / "context_exporter.py")]
        res = subprocess.run(cmd, cwd=self.fixture_root, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Failed: {res.stderr}")
        self.assertIn("Project Context Export Successful", res.stdout)
        exports = list((self.fixture_root / "exports").glob("project-context-*.txt"))
        self.assertTrue(len(exports) >= 1)

    def test_02_run_from_another_directory_succeeds(self):
        """2. Running from another directory succeeds."""
        other_temp = tempfile.TemporaryDirectory()
        try:
            cmd = [
                sys.executable,
                str(self.fixture_root / "tools" / "context_exporter.py"),
                "--project-root",
                str(self.fixture_root),
            ]
            res = subprocess.run(cmd, cwd=other_temp.name, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Failed: {res.stderr}")
            exports = list((self.fixture_root / "exports").glob("project-context-*.txt"))
            self.assertTrue(len(exports) >= 1)
        finally:
            other_temp.cleanup()

    def test_03_export_paths_remain_root_relative(self):
        """3. Export paths remain root-relative; no absolute system paths leaked."""
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()
        # Ensure fixture temp path is not in report
        self.assertNotIn(str(self.fixture_root), report)
        self.assertIn(f"Relative Root Name: {self.fixture_root.name}/", report)
        self.assertIn("FILE: engine.py", report)

    def test_04_venv_is_excluded(self):
        """4. .venv/ directory is strictly excluded."""
        venv_dir = self.fixture_root / ".venv"
        venv_dir.mkdir()
        (venv_dir / "secret_script.py").write_text("SENSITIVE_VENV_DATA = True\n")
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()
        self.assertNotIn("secret_script.py", report)
        self.assertNotIn("SENSITIVE_VENV_DATA", report)

    def test_05_artifacts_is_excluded(self):
        """5. artifacts/ directory contents are excluded."""
        art_dir = self.fixture_root / "artifacts"
        art_dir.mkdir()
        (art_dir / "embeddings.npy").write_bytes(b"\x93NUMPY\x01\x00data")
        (art_dir / "catalog.json").write_text('{"confidential_video": "secret_id"}')
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()
        self.assertNotIn("confidential_video", report)
        self.assertIn("Artifact directory present: Yes", report)
        self.assertIn("Model binary contents: Excluded", report)
        self.assertIn("Embedding arrays: Excluded", report)

    def test_06_nested_model_directories_excluded(self):
        """6. Nested model directories are excluded regardless of nesting."""
        nested = self.fixture_root / "deep" / "nested" / "models"
        nested.mkdir(parents=True)
        (nested / "model_weights.py").write_text("WEIGHTS = [0.1, 0.2]\n")
        exporter = ContextExporter(self.fixture_root)
        discovered = exporter.discover_files()
        discovered_strs = [str(f) for f in discovered]
        for s in discovered_strs:
            self.assertNotIn("models", s)
        report = exporter.generate_report()
        self.assertNotIn("model_weights.py", report)

    def test_07_unknown_model_file_extensions_excluded(self):
        """7. Model/ML extensions (.pt, .safetensors, .onnx, .bin, .h5) are excluded."""
        model_exts = [".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".bin", ".h5", ".gguf"]
        for ext in model_exts:
            (self.fixture_root / f"test_model{ext}").write_bytes(b"dummy model data")
        exporter = ContextExporter(self.fixture_root)
        discovered = exporter.discover_files()
        discovered_names = [f.name for f in discovered]
        for ext in model_exts:
            self.assertNotIn(f"test_model{ext}", discovered_names)

    def test_08_csv_contents_never_exported(self):
        """8. CSV data records are never exported."""
        csv_path = self.fixture_root / "private_dataset.csv"
        csv_path.write_text("Title,URL,SecretNote\nSecretVideoTitle,https://youtube.com/watch?v=123,SensitiveThought\n")
        exporter = ContextExporter(self.fixture_root, strict_mode=True)
        report = exporter.generate_report()
        self.assertNotIn("SecretVideoTitle", report)
        self.assertNotIn("SensitiveThought", report)
        self.assertIn("Strict No-Data-Read Mode: Enabled", report)

    def test_09_symlinks_never_followed(self):
        """9. Symlinks are never followed."""
        external_dir = tempfile.TemporaryDirectory()
        try:
            ext_path = Path(external_dir.name)
            (ext_path / "external_secret.py").write_text("SECRET_EXTERNAL_CODE = 123\n")
            symlink_dir = self.fixture_root / "external_link"
            symlink_dir.symlink_to(ext_path)

            exporter = ContextExporter(self.fixture_root)
            report = exporter.generate_report()
            self.assertNotIn("external_secret.py", report)
            self.assertNotIn("SECRET_EXTERNAL_CODE", report)
        finally:
            external_dir.cleanup()

    def test_10_sensitive_config_files_excluded(self):
        """10. Sensitive files (.env, credentials, secrets, pem, key) are excluded."""
        sensitive_files = [
            ".env",
            ".env.production",
            "aws_credentials.json",
            "jwt_token.txt",
            "private_key.pem",
            "tls_cert.crt",
        ]
        for sfile in sensitive_files:
            (self.fixture_root / sfile).write_text("SECRET_DATA=topsecret\n")

        exporter = ContextExporter(self.fixture_root)
        discovered_names = [f.name for f in exporter.discover_files()]
        for sfile in sensitive_files:
            self.assertNotIn(sfile, discovered_names)

    def test_11_large_source_files_skipped(self):
        """11. Files exceeding 100 KB are skipped and noted."""
        # Test with an approved source file exceeding 100 KB (180 KB)
        large_engine = self.fixture_root / "engine.py"
        large_engine.write_text("# filler\n" + ("x = 1\n" * 30000), encoding="utf-8")
        exporter = ContextExporter(self.fixture_root)
        exporter.discover_files()
        skipped_names = [s[0] for s in exporter.skipped_files]
        self.assertIn("engine.py", skipped_names)
        report = exporter.generate_report()
        self.assertIn("Skipped Files:", report)
        self.assertIn("engine.py", report)
        # Ensure contents of large file are not in Section 10
        self.assertNotIn("FILE: engine.py", report)

    def test_12_total_report_size_below_500kb(self):
        """12. Total report size stays below 500 KB limit."""
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()
        report_bytes = len(report.encode("utf-8"))
        self.assertLessEqual(report_bytes, MAX_REPORT_SIZE)

    def test_13_source_sanitization_removes_secrets_and_paths(self):
        """13. Source sanitization removes representative secrets and absolute home paths."""
        leak_file = self.fixture_root / "engine.py"
        leak_file.write_text(
            '# Config\n'
            'user_path = "/Users/johndoe/projects/myproject"\n'
            'linux_path = "/home/developer/code"\n'
            'api_key = "sk-proj-12345678901234567890abcdef"\n'
            'token = "ghp_123456789012345678901234567890123678"\n'
            'secret_key = "SuperSecretPassword123"\n'
            'auth_header = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy"\n'
            'contact = "dev@example.org"\n',
            encoding="utf-8"
        )
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()

        self.assertNotIn("/Users/johndoe", report)
        self.assertNotIn("/home/developer", report)
        self.assertNotIn("sk-proj-12345678901234567890abcdef", report)
        self.assertNotIn("ghp_123456789012345678901234567890123678", report)
        self.assertNotIn("SuperSecretPassword123", report)
        self.assertNotIn("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy", report)
        self.assertNotIn("dev@example.org", report)

        self.assertIn("<REDACTED_USER_PATH>", report)
        self.assertIn("<REDACTED_API_KEY>", report)
        self.assertIn("<REDACTED_TOKEN>", report)
        self.assertIn("<REDACTED_SECRET>", report)
        self.assertIn("<REDACTED_EMAIL>", report)

    def test_14_api_source_declarations_remain_readable(self):
        """14. API source declarations remain readable and functional after sanitization."""
        exporter = ContextExporter(self.fixture_root)
        report = exporter.generate_report()
        self.assertIn('Route("/health"', report)
        self.assertIn("def recommend(text, top_k=5):", report)

    def test_15_new_model_files_remain_excluded(self):
        """15. Newly introduced model files are excluded by default."""
        new_models = [
            self.fixture_root / "finetuned_model.safetensors",
            self.fixture_root / "llama_weights.gguf",
            self.fixture_root / "custom_vectors.parquet",
        ]
        for nm in new_models:
            nm.write_bytes(b"future model payload")
        exporter = ContextExporter(self.fixture_root)
        discovered = exporter.discover_files()
        names = [f.name for f in discovered]
        for nm in new_models:
            self.assertNotIn(nm.name, names)

    def test_16_exporting_twice_produces_distinct_filenames(self):
        """16. Exporting twice produces distinct files without overwriting."""
        exporter_script = self.fixture_root / "tools" / "context_exporter.py"
        cmd = [sys.executable, str(exporter_script)]

        res1 = subprocess.run(cmd, cwd=self.fixture_root, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0)
        res2 = subprocess.run(cmd, cwd=self.fixture_root, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0)

        exports = sorted(list((self.fixture_root / "exports").glob("project-context-*.txt")))
        self.assertGreaterEqual(len(exports), 2, "Expected at least 2 distinct export files")
        self.assertNotEqual(exports[0].name, exports[1].name)

    def test_17_existing_application_code_and_artifacts_remain_unchanged(self):
        """17. Existing application code and artifacts remain untouched."""
        def calc_hashes():
            hashes = {}
            for fname in ["build_index.py", "engine.py", "server.py", "ui.py", "requirements.txt"]:
                p = PROJECT_ROOT / fname
                if p.exists():
                    hashes[fname] = hashlib.sha256(p.read_bytes()).hexdigest()
            return hashes

        initial_hashes = calc_hashes()
        # Run export on real project root
        cmd = [sys.executable, str(PROJECT_ROOT / "tools" / "context_exporter.py"), "--project-root", str(PROJECT_ROOT), "--check"]
        subprocess.run(cmd, capture_output=True, check=True)
        final_hashes = calc_hashes()

        self.assertEqual(initial_hashes, final_hashes, "Project source code was modified!")


if __name__ == "__main__":
    unittest.main()
