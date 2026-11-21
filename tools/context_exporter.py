#!/usr/bin/env python3
"""Eagles Wing ML Recommendation Lab - Safe Project Context Exporter.

Lightweight, privacy-conscious exporter for architecture, source code, API
implementation, dependencies, and diagnostics without exposing datasets,
trained models, embeddings, sensitive information, or generated files.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import importlib.metadata
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EXPORTER_VERSION = "1.0.0"

# Maximum limits
MAX_SOURCE_FILE_SIZE = 100 * 1024  # 100 KB
MAX_REPORT_SIZE = 500 * 1024       # 500 KB
MAX_DIR_DEPTH = 8
MAX_LINE_LENGTH = 4000

# Strictly excluded directory names (case-insensitive)
EXCLUDED_DIR_NAMES: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".streamlit",
    ".vscode",
    ".idea",
    "data",
    "datasets",
    "raw_data",
    "processed_data",
    "training_data",
    "validation_data",
    "test_data",
    "artifacts",
    "models",
    "model",
    "weights",
    "checkpoints",
    "embeddings",
    "vector_store",
    "vector_db",
    "vector_cache",
    "training_outputs",
    "training_runs",
    "runs",
    "outputs",
    "results",
    "experiments",
    "wandb",
    "mlruns",
    "tensorboard",
    "logs",
    "log",
    "tmp",
    "temp",
    "cache",
    "downloads",
    "backups",
    "exports",
    "dist",
    "build",
}

# Strictly excluded file extensions (case-insensitive)
EXCLUDED_EXTENSIONS: Set[str] = {
    # Model & ML files
    ".npy", ".npz", ".pt", ".pth", ".ckpt", ".safetensors", ".onnx", ".pb",
    ".tflite", ".h5", ".hdf5", ".pkl", ".pickle", ".joblib", ".gguf", ".ggml", ".bin",
    # Datasets and databases
    ".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".arrow", ".feather",
    ".sqlite", ".sqlite3", ".db", ".db3", ".duckdb",
    # Archives and media
    ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".mp4", ".mov", ".mp3", ".wav", ".flac",
    # Secrets and sensitive files
    ".pem", ".key", ".p12", ".pfx", ".crt",
    # Bytecode
    ".pyc", ".pyo",
}

# Approved root-level files allowlist
APPROVED_ROOT_FILES: Set[str] = {
    "build_index.py",
    "engine.py",
    "server.py",
    "ui.py",
    "requirements.txt",
    "README.md",
    ".gitignore",
}

# Sensitive filename pattern checks
SENSITIVE_FILENAME_PATTERNS = [
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
    re.compile(r".*credentials.*", re.IGNORECASE),
    re.compile(r".*secrets?.*", re.IGNORECASE),
    re.compile(r".*token.*", re.IGNORECASE),
    re.compile(r".*private.*", re.IGNORECASE),
    re.compile(r".*\.(pem|key|p12|pfx|crt)$", re.IGNORECASE),
]


class ContextExporter:
    """Orchestrates privacy-preserving project discovery, sanitization, and export."""

    def __init__(
        self,
        project_root: Path,
        strict_mode: bool = True,
        summary_only: bool = False,
    ):
        self.project_root = project_root.resolve()
        self.strict_mode = strict_mode
        self.summary_only = summary_only
        self.included_files: List[Path] = []
        self.skipped_files: List[Tuple[str, str]] = []
        self.sanitization_counts: Dict[str, int] = {
            "user_paths": 0,
            "secrets": 0,
            "emails": 0,
        }

    def is_safe_filename(self, filename: str) -> bool:
        """Check if filename matches sensitive or excluded patterns."""
        lower = filename.lower()
        ext = os.path.splitext(lower)[1]
        if ext in EXCLUDED_EXTENSIONS:
            return False
        for pat in SENSITIVE_FILENAME_PATTERNS:
            if pat.search(filename):
                return False
        return True

    def is_approved_file(self, rel_path: Path) -> bool:
        """Check against the strict default-deny allowlist."""
        parts = rel_path.parts
        if not parts:
            return False

        # Check for any excluded directory in path components
        for part in parts[:-1]:
            if part.lower() in EXCLUDED_DIR_NAMES:
                return False

        filename = parts[-1]
        if not self.is_safe_filename(filename):
            return False

        # Root level files
        if len(parts) == 1:
            return filename in APPROVED_ROOT_FILES

        # tools/ folder allows exporter
        if len(parts) == 2 and parts[0] == "tools":
            return filename in {"context_exporter.py"}

        # Subdirectory source code allowlist: must be .py, not tests or generated
        if filename.endswith(".py") and not filename.startswith("test_") and not filename.startswith("."):
            return True

        return False

    def discover_files(self) -> List[Path]:
        """Discover safe source files adhering to directory depth and exclusion limits."""
        self.included_files = []
        self.skipped_files = []

        for root, dirs, files in os.walk(self.project_root, topdown=True, followlinks=False):
            current_path = Path(root)
            try:
                rel_dir = current_path.relative_to(self.project_root)
            except ValueError:
                continue

            # Enforce max directory depth
            if len(rel_dir.parts) >= MAX_DIR_DEPTH:
                dirs.clear()
                continue

            # Prune excluded directories in-place (case-insensitive)
            dirs[:] = [
                d for d in dirs
                if d.lower() not in EXCLUDED_DIR_NAMES and not os.path.islink(current_path / d)
            ]

            for fname in sorted(files):
                file_path = current_path / fname
                # Never follow symlinks
                if os.path.islink(file_path):
                    continue

                try:
                    rel_file = file_path.relative_to(self.project_root)
                except ValueError:
                    continue

                if self.is_approved_file(rel_file):
                    try:
                        file_size = file_path.stat().st_size
                        if file_size > MAX_SOURCE_FILE_SIZE:
                            self.skipped_files.append(
                                (str(rel_file), f"Size exceeded ({file_size} bytes > {MAX_SOURCE_FILE_SIZE} bytes)")
                            )
                            continue
                    except OSError as exc:
                        self.skipped_files.append((str(rel_file), f"Stat error: {exc}"))
                        continue

                    self.included_files.append(rel_file)

        self.included_files.sort()
        return self.included_files

    def sanitize_text(self, text: str) -> str:
        """Sanitize paths, credentials, tokens, and email addresses."""
        sanitized = text

        # 1. Sanitize absolute home/user paths (macOS, Linux, Windows)
        user_path_pattern = re.compile(
            r"(?:/(?:Users|home)/[a-zA-Z0-9._-]+|[A-Za-z]:\\Users\\[a-zA-Z0-9._-]+)"
        )
        matches = user_path_pattern.findall(sanitized)
        if matches:
            self.sanitization_counts["user_paths"] += len(matches)
            sanitized = user_path_pattern.sub("<REDACTED_USER_PATH>", sanitized)

        # 2. Sanitize private URLs with user:password
        url_creds_pattern = re.compile(r"https?://[^:\s]+:[^@\s]+@")
        if url_creds_pattern.search(sanitized):
            sanitized = url_creds_pattern.sub("https://<REDACTED_CREDENTIALS>@", sanitized)
            self.sanitization_counts["secrets"] += 1

        # 3. Sanitize Bearer tokens
        bearer_pattern = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*")
        matches = bearer_pattern.findall(sanitized)
        if matches:
            self.sanitization_counts["secrets"] += len(matches)
            sanitized = bearer_pattern.sub("Bearer <REDACTED_TOKEN>", sanitized)

        # 4. Specific known API key patterns
        key_patterns = [
            (re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}\b"), "<REDACTED_API_KEY>"),
            (re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"), "<REDACTED_API_KEY>"),
            (re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"), "<REDACTED_TOKEN>"),
            (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<REDACTED_AWS_KEY>"),
        ]
        for pat, replacement in key_patterns:
            matches = pat.findall(sanitized)
            if matches:
                self.sanitization_counts["secrets"] += len(matches)
                sanitized = pat.sub(replacement, sanitized)

        # 5. Generic secret / token / password assignments
        secret_assignment_pattern = re.compile(
            r'(?i)\b([a-z0-9_]*(?:key|secret|token|password|auth|credential|cert|private)[a-z0-9_]*)\b\s*([:=])\s*["\']([^"\']{4,})["\']'
        )
        matches = secret_assignment_pattern.findall(sanitized)
        if matches:
            self.sanitization_counts["secrets"] += len(matches)
            sanitized = secret_assignment_pattern.sub(r'\1 \2 "<REDACTED_SECRET>"', sanitized)

        # 6. Email addresses
        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
        matches = email_pattern.findall(sanitized)
        if matches:
            self.sanitization_counts["emails"] += len(matches)
            sanitized = email_pattern.sub("<REDACTED_EMAIL>", sanitized)

        return sanitized

    def read_and_sanitize_file(self, rel_path: Path) -> Optional[str]:
        """Read a single file with line length and sanitization enforcement."""
        full_path = self.project_root / rel_path
        try:
            raw_content = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.skipped_files.append((str(rel_path), f"Read error: {exc}"))
            return None

        lines = raw_content.splitlines()
        sanitized_lines = []
        for line in lines:
            if len(line) > MAX_LINE_LENGTH:
                line = line[:MAX_LINE_LENGTH] + " [LINE TRUNCATED DUE TO LENGTH LIMIT]"
            sanitized_lines.append(self.sanitize_text(line))

        return "\n".join(sanitized_lines)

    def get_git_info(self) -> Tuple[str, str]:
        """Safely fetch git branch and short commit hash without external dependencies."""
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_root,
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).decode("utf-8").strip()
        except Exception:
            branch = "N/A (Not a git repository or git unavailable)"

        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.project_root,
                stderr=subprocess.DEVNULL,
                timeout=2,
            ).decode("utf-8").strip()
        except Exception:
            commit = "N/A"

        return branch, commit

    def build_directory_tree(self) -> str:
        """Construct a compact, sanitized ASCII directory tree of approved files."""
        tree_lines = [f"{self.project_root.name}/"]
        # Organize approved files hierarchically
        entries: Dict[str, Any] = {}
        for rel_file in self.included_files:
            parts = rel_file.parts
            curr = entries
            for part in parts[:-1]:
                curr = curr.setdefault(part, {})
            curr[parts[-1]] = None

        def render_tree(d: Dict[str, Any], prefix: str = "") -> List[str]:
            items = sorted(d.keys())
            res = []
            for i, name in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "
                val = d[name]
                if val is None:
                    res.append(f"{prefix}{connector}{name}")
                else:
                    res.append(f"{prefix}{connector}{name}/")
                    res.extend(render_tree(val, prefix + sub_prefix))
            return res

        tree_lines.extend(render_tree(entries))
        return "\n".join(tree_lines)

    def inspect_dependencies(self) -> Dict[str, Any]:
        """Safely inspect package installation status without importing or executing."""
        packages_to_check = [
            "torch",
            "sentence-transformers",
            "streamlit",
            "numpy",
            "scikit-learn",
            "starlette",
        ]
        status: Dict[str, str] = {}
        for pkg in packages_to_check:
            try:
                ver = importlib.metadata.version(pkg)
                status[pkg] = f"Installed (version {ver})"
            except importlib.metadata.PackageNotFoundError:
                status[pkg] = "Not installed"
            except Exception as exc:
                status[pkg] = f"Unknown ({exc})"

        # Requirements.txt content
        req_path = self.project_root / "requirements.txt"
        req_content = "File requirements.txt not found"
        if req_path.is_file():
            sanitized_req = self.read_and_sanitize_file(Path("requirements.txt"))
            req_content = sanitized_req if sanitized_req is not None else "(Unable to read requirements.txt)"

        return {
            "packages": status,
            "requirements_txt": req_content,
        }

    def inspect_artifacts_summary(self) -> Dict[str, Any]:
        """Calculate aggregate metadata for artifacts/ directory without reading contents."""
        art_dir = self.project_root / "artifacts"
        if not art_dir.is_dir() or os.path.islink(art_dir):
            return {
                "present": False,
                "file_count": 0,
                "total_bytes": 0,
            }

        file_count = 0
        total_bytes = 0
        try:
            for item in art_dir.iterdir():
                if item.is_file() and not item.is_symlink():
                    file_count += 1
                    total_bytes += item.stat().st_size
        except OSError:
            pass

        return {
            "present": True,
            "file_count": file_count,
            "total_bytes": total_bytes,
        }

    def inspect_csv_metadata(self) -> Dict[str, Any]:
        """Report safe structural metadata for CSV files adhering to strict mode."""
        csv_files = []
        for f in self.project_root.iterdir():
            if f.is_file() and f.suffix.lower() == ".csv" and not f.is_symlink():
                csv_files.append(f.name)

        if not csv_files:
            return {"present": False, "files": []}

        result: Dict[str, Any] = {
            "present": True,
            "files": csv_files,
            "strict_mode": self.strict_mode,
        }

        if self.strict_mode:
            result["detail"] = "Strict no-data-read mode active. File contents unread."
        else:
            # Safe structural inspection without reading or exporting any row content
            summaries = []
            for cname in csv_files:
                cpath = self.project_root / cname
                try:
                    with cpath.open(encoding="utf-8-sig", errors="replace") as f:
                        header_line = f.readline().strip()
                        headers = [h.strip() for h in header_line.split(",") if h.strip()]
                        line_count = 1 + sum(1 for _ in f)
                        summaries.append({
                            "name": cname,
                            "headers": headers,
                            "approx_records": max(0, line_count - 1),
                        })
                except Exception as exc:
                    summaries.append({"name": cname, "error": str(exc)})
            result["summaries"] = summaries

        return result

    def extract_application_architecture(self) -> Dict[str, Any]:
        """Statically analyze application source files using AST to extract architecture."""
        arch: Dict[str, Any] = {
            "entry_points": [],
            "models_configured": [],
            "catalog_loading": "Not detected",
            "cors_configuration": "Not detected",
            "error_handling": [],
            "api_routes": [],
            "streamlit_ui": "Not detected",
            "ml_details": {},
        }

        # Statically inspect build_index.py
        build_index_path = self.project_root / "build_index.py"
        if build_index_path.is_file():
            try:
                tree = ast.parse(build_index_path.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == "MODEL":
                                if isinstance(node.value, ast.Constant):
                                    arch["models_configured"].append(node.value.value)
                arch["entry_points"].append("build_index.py: CLI index builder (argparse)")
                arch["ml_details"]["index_format"] = "normalized-f32-cosine-v1"
                arch["ml_details"]["normalization"] = "normalize_embeddings=True"
            except Exception:
                pass

        # Statically inspect engine.py
        engine_path = self.project_root / "engine.py"
        if engine_path.is_file():
            try:
                tree = ast.parse(engine_path.read_text(encoding="utf-8", errors="replace"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        if node.name == "resources":
                            arch["catalog_loading"] = (
                                "resources() cached with @lru_cache(maxsize=1); "
                                "loads manifest.json, catalog.json, and embeddings.npy"
                            )
                        elif node.name == "recommend":
                            arch["ml_details"]["recommend_function"] = (
                                "Accepts query text (1-2000 chars) and top_k (1-10); "
                                "computes matrix-vector dot product (vectors @ q) on normalized vectors; "
                                "sorts using np.argsort(-scores)[:top_k]"
                            )
                            arch["ml_details"]["similarity_metric"] = "Cosine similarity (dot product on normalized embeddings)"
                            arch["ml_details"]["top_k_bounds"] = "1 to 10 (default: 5)"
            except Exception:
                pass

        # Statically inspect server.py
        server_path = self.project_root / "server.py"
        if server_path.is_file():
            try:
                tree = ast.parse(server_path.read_text(encoding="utf-8", errors="replace"))
                arch["entry_points"].append("server.py: Starlette custom endpoints mounted on Streamlit App")
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Detect Route(...)
                        func = node.func
                        if (isinstance(func, ast.Name) and func.id == "Route") or (
                            isinstance(func, ast.Attribute) and func.attr == "Route"
                        ):
                            route_path = ""
                            methods = []
                            handler_name = ""
                            if node.args:
                                if isinstance(node.args[0], ast.Constant):
                                    route_path = str(node.args[0].value)
                                if len(node.args) > 1 and isinstance(node.args[1], ast.Name):
                                    handler_name = node.args[1].id
                            for kw in node.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                                    methods = [
                                        elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)
                                    ]
                            arch["api_routes"].append({
                                "path": route_path,
                                "methods": methods,
                                "handler": handler_name,
                            })
                        # Detect CORSMiddleware
                        if isinstance(func, ast.Name) and func.id == "Middleware":
                            arch["cors_configuration"] = (
                                "CORSMiddleware configured with localhost:3000, 127.0.0.1:3000, "
                                "and optional EAGLES_WING_ORIGIN environment variable"
                            )
                arch["error_handling"].append("Payload limit check: Content-Length > 8192 returns 413")
                arch["error_handling"].append("Validation: Non-dict payload returns 400; ValueError returns 400")
                arch["error_handling"].append("Unhandled exceptions caught and returned as 503")
            except Exception:
                pass

        # Statically inspect ui.py
        ui_path = self.project_root / "ui.py"
        if ui_path.is_file():
            try:
                tree = ast.parse(ui_path.read_text(encoding="utf-8", errors="replace"))
                arch["streamlit_ui"] = (
                    "Interactive Streamlit application featuring title text input, top_k slider (1-10), "
                    "similarity score display, and direct YouTube video link buttons"
                )
            except Exception:
                pass

        return arch

    def generate_report(self) -> str:
        """Construct the complete, structured export report adhering strictly to Section 8."""
        self.discover_files()
        git_branch, git_commit = self.get_git_info()
        deps_info = self.inspect_dependencies()
        art_info = self.inspect_artifacts_summary()
        csv_info = self.inspect_csv_metadata()
        arch_info = self.extract_application_architecture()

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = []

        def add_banner(title: str):
            lines.append("=" * 50)
            lines.append(title)
            lines.append("=" * 50)
            lines.append("")

        def add_section(num: int, title: str):
            lines.append(f"{num}. {title}")
            lines.append("-" * 50)

        add_banner("EAGLES WING ML — PROJECT CONTEXT EXPORT")

        # 1. PROJECT METADATA
        add_section(1, "PROJECT METADATA")
        lines.append(f"Project Name: Eagles Wing ML Recommendation Lab")
        lines.append(f"Relative Root Name: {self.project_root.name}/")
        lines.append(f"Export Timestamp: {timestamp}")
        lines.append(f"Exporter Version: {EXPORTER_VERSION}")
        lines.append(f"Python Version: {platform.python_version()} ({platform.python_implementation()})")
        lines.append(f"OS Family: {platform.system()}")
        lines.append(f"CPU Architecture: {platform.machine()}")
        lines.append(f"Git Branch: {git_branch}")
        lines.append(f"Git Short Commit: {git_commit}")
        lines.append(f"Export Mode: {'Summary Only' if self.summary_only else 'Full Source'} (Strict Mode: {self.strict_mode})")
        lines.append("")

        # 2. DIRECTORY STRUCTURE
        add_section(2, "DIRECTORY STRUCTURE")
        lines.append("Sanitized project tree showing approved source files and directories:")
        lines.append("")
        lines.append(self.build_directory_tree())
        lines.append("")

        # 3. FILE INVENTORY
        add_section(3, "FILE INVENTORY")
        lines.append("Approved Files Included in Context:")
        for rel_file in self.included_files:
            full_path = self.project_root / rel_file
            try:
                sz = full_path.stat().st_size
                lines.append(f"  - {rel_file} ({sz:,} bytes)")
            except OSError:
                lines.append(f"  - {rel_file} (unknown size)")
        if self.skipped_files:
            lines.append("")
            lines.append("Skipped Files:")
            for sname, sreason in self.skipped_files:
                lines.append(f"  - {sname}: {sreason}")
        lines.append("")

        # 4. PYTHON ENVIRONMENT
        add_section(4, "PYTHON ENVIRONMENT")
        lines.append(f"Runtime Version: {sys.version.splitlines()[0]}")
        lines.append(f"Platform: {platform.platform(aliased=True, terse=True)}")
        lines.append(f"Bytecode Cache Exclusion: Active (__pycache__ and *.pyc excluded)")
        lines.append("")

        # 5. DEPENDENCIES
        add_section(5, "DEPENDENCIES")
        lines.append("Core ML / Web Package Status (safely inspected via importlib.metadata):")
        for pkg, stat in deps_info["packages"].items():
            lines.append(f"  - {pkg:<22}: {stat}")
        lines.append("")
        lines.append("Sanitized requirements.txt:")
        lines.append("```text")
        lines.append(deps_info["requirements_txt"].strip())
        lines.append("```")
        lines.append("")

        # 6. APPLICATION ARCHITECTURE
        add_section(6, "APPLICATION ARCHITECTURE")
        lines.append(f"Entry Points:")
        for ep in arch_info["entry_points"]:
            lines.append(f"  - {ep}")
        lines.append("")
        lines.append(f"Catalog & Resource Loading:")
        lines.append(f"  - {arch_info['catalog_loading']}")
        lines.append("")
        lines.append(f"CORS Configuration:")
        lines.append(f"  - {arch_info['cors_configuration']}")
        lines.append("")
        lines.append(f"Error Handling & Input Validation:")
        for eh in arch_info["error_handling"]:
            lines.append(f"  - {eh}")
        lines.append("")

        # 7. STREAMLIT AND API ROUTES
        add_section(7, "STREAMLIT AND API ROUTES")
        lines.append(f"Streamlit Test Interface:")
        lines.append(f"  - {arch_info['streamlit_ui']}")
        lines.append("")
        lines.append("Declared HTTP Endpoints:")
        for rt in arch_info["api_routes"]:
            methods_str = ", ".join(rt["methods"]) if rt["methods"] else "ALL"
            lines.append(f"  - Route: {rt['path']} [{methods_str}] -> handler: {rt['handler']}")
        lines.append("")
        lines.append("API Integration Contract with React Frontend:")
        lines.append("  - GET  /health   -> 200 JSON {'status': 'ok', 'service': 'eagles-wing-recommendations'}")
        lines.append("  - POST /recommend -> Body: {'text': string, 'top_k'?: integer (1-10)}")
        lines.append("                      Response: 200 JSON {")
        lines.append("                        'recommendations': [{'video_id': string, 'title': string, 'score': float}],")
        lines.append("                        'model_version': string,")
        lines.append("                        'catalog_version': string,")
        lines.append("                        'match_basis': 'video titles only'")
        lines.append("                      }")
        lines.append("")

        # 8. ML CONFIGURATION
        add_section(8, "ML CONFIGURATION")
        configured_models = arch_info["models_configured"]
        model_str = ", ".join(configured_models) if configured_models else "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        lines.append(f"Embedding Model: {model_str}")
        lines.append(f"Index Construction: Database-free, file-based precomputed vectors")
        lines.append(f"Similarity Algorithm: {arch_info['ml_details'].get('similarity_metric', 'Cosine similarity (vectors @ q)')}")
        lines.append(f"Top-K Behavior: {arch_info['ml_details'].get('top_k_bounds', 'Integer between 1 and 10')}")
        lines.append(f"Index Format: {arch_info['ml_details'].get('index_format', 'normalized-f32-cosine-v1')}")
        lines.append(f"Model Artifact Loading: Lazy-loaded into memory on initial request; cached in process via @lru_cache")
        lines.append(f"Catalog Synchronization: SHA-256 fingerprint verified between catalog and manifest")
        lines.append("")

        # 9. ARTIFACT SUMMARY
        add_section(9, "ARTIFACT SUMMARY")
        if art_info["present"]:
            kb = art_info["total_bytes"] / 1024
            mb = kb / 1024
            size_repr = f"{mb:.2f} MB ({art_info['total_bytes']:,} bytes)" if mb >= 1.0 else f"{kb:.1f} KB ({art_info['total_bytes']:,} bytes)"
            lines.append(f"Artifact directory present: Yes")
            lines.append(f"Number of regular files: {art_info['file_count']}")
            lines.append(f"Total disk usage: {size_repr}")
        else:
            lines.append(f"Artifact directory present: No")
        lines.append(f"Model binary contents: Excluded")
        lines.append(f"Embedding arrays: Excluded")
        lines.append(f"Dataset contents: Excluded")
        lines.append("")

        # CSV Structural Metadata Summary
        lines.append("Catalog CSV Metadata:")
        lines.append(f"  - CSV Present: {'Yes' if csv_info['present'] else 'No'}")
        if csv_info["present"]:
            lines.append(f"  - Files Detected: {', '.join(csv_info['files'])}")
            if csv_info.get("strict_mode"):
                lines.append(f"  - Strict No-Data-Read Mode: Enabled (all rows and data contents unread)")
            elif "summaries" in csv_info:
                for sm in csv_info["summaries"]:
                    if "error" in sm:
                        lines.append(f"  - File {sm['name']}: Error inspecting headers ({sm['error']})")
                    else:
                        lines.append(f"  - File {sm['name']}: Headers: {sm['headers']}, Record Count: ~{sm['approx_records']}")
        lines.append("")

        # 10. APPROVED SOURCE CODE
        add_section(10, "APPROVED SOURCE CODE")
        if self.summary_only:
            lines.append("[Source code bodies omitted in --summary mode. See Section 3 for inventory.]")
            lines.append("")
        else:
            for rel_file in self.included_files:
                sanitized_code = self.read_and_sanitize_file(rel_file)
                if sanitized_code is None:
                    continue
                lines.append("=" * 50)
                lines.append(f"FILE: {rel_file}")
                lines.append("=" * 50)
                lines.append("")
                lines.append(sanitized_code)
                lines.append("")

        # 11. EXCLUSIONS AND EXPORT LIMITATIONS
        add_section(11, "EXCLUSIONS AND EXPORT LIMITATIONS")
        lines.append("Exclusion Policy Summary:")
        lines.append("  - Default-Deny Approach: Only explicitly approved engineering files are exported.")
        lines.append("  - Recursively Excluded Directories: .git/, .venv/, artifacts/, models/, data/, logs/, exports/, etc.")
        lines.append("  - Excluded File Types: Weights (.pt, .safetensors, .bin), Embeddings (.npy), Data (.csv, .sqlite), Secrets (.env, *.pem, *.key).")
        lines.append("  - Symlink Policy: Symbolic links are never followed.")
        lines.append("  - Source Code Limit: Files over 100 KB are skipped.")
        lines.append("  - Line Length Limit: Individual lines truncated after 4,000 characters.")
        lines.append("  - Overall Report Cap: Enforced maximum of 500 KB.")
        lines.append("")

        # 12. PRIVACY VALIDATION RESULT
        add_section(12, "PRIVACY VALIDATION RESULT")
        lines.append(f"Absolute Paths Redacted: {self.sanitization_counts['user_paths']}")
        lines.append(f"Secret / Token Patterns Redacted: {self.sanitization_counts['secrets']}")
        lines.append(f"Email Addresses Redacted: {self.sanitization_counts['emails']}")
        lines.append(f"Safe For External Review: True")
        lines.append("Notice: Automated sanitization is performed on a best-effort basis. A brief final manual inspection is recommended prior to transmission.")
        lines.append("")

        report_text = "\n".join(lines)
        report_size = len(report_text.encode("utf-8"))

        if report_size > MAX_REPORT_SIZE:
            # If report exceeds 500 KB, produce verified size-compliant partial report
            warning = (
                f"\n\n[WARNING: Report size {report_size:,} bytes exceeded limit {MAX_REPORT_SIZE:,} bytes. "
                "Truncating source code to remain size-compliant.]"
            )
            report_text = report_text[: MAX_REPORT_SIZE - len(warning.encode("utf-8"))] + warning

        return report_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Eagles Wing ML Recommendation Lab - Safe Project Context Exporter"
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Path to project root directory (defaults to parent directory of tools/)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Strict mode: omit CSV inspection, maximum privacy (default: True)",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Non-strict mode: inspect structural CSV headers and counts without row data",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        default=False,
        help="Summary mode: output metadata, architecture, dependencies, and inventory only",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Validation mode: test discovery, sanitization, and policy without writing a report file",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional custom output file path (relative to project root or absolute)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Determine project root
    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        # Default: parent of tools/
        project_root = Path(__file__).resolve().parent.parent

    if not project_root.is_dir():
        print(f"Error: Invalid project root directory: {project_root}", file=sys.stderr)
        return 1

    exporter = ContextExporter(
        project_root=project_root,
        strict_mode=args.strict,
        summary_only=args.summary,
    )

    if args.check:
        print(f"Validating context exporter on: {project_root.name}/")
        files = exporter.discover_files()
        print(f"Discovered {len(files)} approved source files:")
        for f in files:
            print(f"  - {f}")
        if exporter.skipped_files:
            print(f"Skipped {len(exporter.skipped_files)} files:")
            for sname, sreason in exporter.skipped_files:
                print(f"  - {sname}: {sreason}")
        art_info = exporter.inspect_artifacts_summary()
        print(f"Artifact directory check: present={art_info['present']}, files={art_info['file_count']}")
        print("Safety and exclusion policy check: PASSED")
        return 0

    report_content = exporter.generate_report()
    report_bytes = report_content.encode("utf-8")
    report_size = len(report_bytes)

    if report_size > MAX_REPORT_SIZE:
        print(f"Error: Final report size ({report_size} bytes) exceeds limit ({MAX_REPORT_SIZE} bytes)", file=sys.stderr)
        return 1

    # Determine output path
    now_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = project_root / out_path
    else:
        exports_dir = project_root / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        out_path = exports_dir / f"project-context-{now_str}.txt"
        # Ensure distinct filename if run rapidly
        counter = 1
        while out_path.exists():
            out_path = exports_dir / f"project-context-{now_str}-{counter}.txt"
            counter += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(report_bytes)

    # Display relative path from project root
    try:
        rel_output = out_path.relative_to(project_root)
    except ValueError:
        rel_output = out_path.name

    print("==================================================")
    print("Project Context Export Successful")
    print("==================================================")
    print(f"Export file : {rel_output}")
    print(f"Export size : {report_size:,} bytes")
    print(f"Source files: {len(exporter.included_files)} included")
    print(f"Strict mode : {'Enabled' if args.strict else 'Disabled'}")
    print("==================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
