# Streamlit Community Cloud Deployment Readiness Report: Eagles Wing ML

**Repository:** `pathto493/links_recommender`  
**Branch:** `main`  
**Assessment Date:** 2026-11-21  
**Deployment Status:** **READY (Pending Git Push to GitHub)**

---

## Executive Summary

Streamlit Community Cloud failed to deploy with the error:
> **`"This file does not exist"`**

This investigation identified two interrelated root causes:
1. **Cloud Configuration Mismatch:** Streamlit Community Cloud's "Main file path" setting was left at the default placeholder `streamlit_app.py`, whereas the project's actual entrypoint is `server.py`.
2. **Unpushed Local Commits:** On remote GitHub `origin/main` (`pathto493/links_recommender`), only `README.md` was present (`commit 4ce7390`). The entire application suite (`server.py`, `ui.py`, `engine.py`, `requirements.txt`, and `artifacts/*`) had been committed locally (`commit 4280312`) but **never pushed to GitHub**. Thus, Streamlit Cloud could not find `streamlit_app.py` or `server.py`.

All local components, including the custom ASGI Starlette endpoints (`/health`, `/recommend`), the Streamlit UI (`ui.py`), and the MiniLM embedding model inference pipeline, were tested and validated with 100% pass rates.

---

## 1. Root Cause Analysis

| Factor | Current State | Impact |
| :--- | :--- | :--- |
| **Streamlit Cloud Config** | `Main file path: streamlit_app.py` | Streamlit Cloud looks for `streamlit_app.py` at the repo root. No such file exists. |
| **GitHub Remote (`origin/main`)** | Commit `4ce7390a` (`README.md` only) | Neither `streamlit_app.py` nor `server.py` existed on GitHub. Streamlit Cloud cloned an empty shell containing only `README.md`. |
| **Local Git HEAD (`main`)** | Commit `42803129` + `db8bf34` | Full application code and precomputed ML artifacts were committed locally but unpushed. |

---

## 2. Configuration Settings Required in Streamlit Community Cloud

When editing app settings in [share.streamlit.io](https://share.streamlit.io):

* **Repository:** `pathto493/links_recommender`
* **Branch:** `main`
* **Main file path:** `server.py`

*(Do NOT create or enter `streamlit_app.py`; `server.py` is the architecturally intended entrypoint that wires the Starlette ASGI custom routes and wraps `ui.py` via `st.App`).*

---

## 3. Repository & Git Status Audit

* **Repository Identity:** Confirmed `https://github.com/pathto493/links_recommender.git`
* **Active Branch:** `main`
* **Local Commits Ahead of Remote:** 2 commits ahead of `origin/main`
  * `4280312` — *first commit* (added `server.py`, `ui.py`, `engine.py`, `requirements.txt`, `artifacts/*`, dataset, scripts, tests)
  * `db8bf34` — *build: ignore generated exports directory* (added `exports/` to `.gitignore`)
* **Tracking Status of Essential Files:**
  * `server.py`: Tracked and committed.
  * `ui.py`: Tracked and committed.
  * `engine.py`: Tracked and committed.
  * `requirements.txt`: Tracked and committed.
  * `artifacts/catalog.json`: Tracked and committed (1,225 records).
  * `artifacts/embeddings.npy`: Tracked and committed (1.88 MB float32 vector matrix).
  * `artifacts/manifest.json`: Tracked and committed.
  * `YoutubeLinksWithInfo - Sheet1.csv`: Tracked and committed (190 KB, 1,313 rows).
* **`.gitignore` Audit:** Verified clean. Safely excludes `.venv/`, `__pycache__/`, `*.pyc`, `.DS_Store`, `.env`, `.streamlit/secrets.toml`, and `exports/`. No essential application or artifact files are excluded.
* **Sensitive File Audit:** Confirmed no `.env`, API keys, tokens, credentials, virtualenvs, or private reflection logs are committed or staged.

---

## 4. Changes Implemented

1. **`.gitignore` Hardening:** Added `exports/` pattern to `.gitignore` and committed in scoped commit `db8bf34`. This prevents any future test context export dumps from entering Git.
2. **No Code Modification Necessary to Core Engine or Server:**
   * `server.py` uses modern Streamlit 1.58+ `st.App("ui.py", routes=[...], middleware=[...])`, which runs seamlessly as an ASGI application on Streamlit Community Cloud.
   * `engine.py` correctly uses `Path(__file__).resolve().parent / "artifacts"` to load index files relative to source code without hardcoded absolute paths.
   * `requirements.txt` correctly pins `streamlit>=1.58,<2`, `sentence-transformers>=3,<6`, `numpy>=1.26,<3`, and `starlette>=0.40,<2`.

---

## 5. Local Validation & Verification Test Results

All 9 validation stages passed without errors:

| Test Item | Verification Method | Status | Observation / Output |
| :--- | :--- | :---: | :--- |
| **1. Python Syntax** | `py_compile` across `server.py`, `ui.py`, `engine.py`, `build_index.py` | **PASS** | 0 syntax errors or warnings. |
| **2. Dependencies** | Environment check via `pip check` and version inspection | **PASS** | `streamlit 1.67.0`, `sentence-transformers 5.7.0`, `starlette 1.10.0`, `numpy 2.5.5`. No broken requirements. |
| **3. Streamlit Entrypoint Import** | Import `server` and inspect `server.app` ASGI instance | **PASS** | `st.App` initialized with `script_path="ui.py"`. |
| **4. Model Artifact Loading** | Integrity check between `manifest.json`, `catalog.json`, and `embeddings.npy` | **PASS** | 1,225 catalog records match 1,225 embedding vectors (dimension 384, float32, cosine normalized). |
| **5. Recommendation Inference** | Offline similarity calculation using `engine.recommend()` | **PASS** | Top-k vector similarity ranking completed in CPU mode with exact semantic matches. |
| **6. YouTube Video ID & URL** | URL reconstruction audit | **PASS** | 11-character video IDs validate correctly; formats to `https://www.youtube.com/watch?v=<video_id>`. |
| **7. `/health` Endpoint** | Live HTTP GET check via Uvicorn/Starlette ASGI | **PASS** | `HTTP 200 OK` → `{"status": "ok", "service": "eagles-wing-recommendations"}`. |
| **8. `/recommend` Endpoint** | Live HTTP POST check via Starlette `TestClient` and `curl` | **PASS** | `HTTP 200 OK` returning structured JSON recommendations, model version, and catalog version. Also confirmed 413 on payload > 8KB and 400 on bad inputs. |
| **9. Streamlit UI Test** | App test execution via `streamlit.testing.v1.AppTest` | **PASS** | Title, text area, slider, and recommendation link buttons rendered as expected. |

---

## 6. Deployment Readiness Assessment

* **Overall Deployment Status:** **READY**
* **Unresolved Deployment Blockers:** None inside the codebase. The only pending action is publishing the local commits to GitHub and updating the Streamlit Cloud app settings.

---

## 7. Action Plan: Exact Git & Publishing Commands

Because explicit approval is required before pushing to GitHub, run the following commands when ready:

```bash
# 1. Inspect unpushed commits
git log --oneline origin/main..HEAD

# 2. Push commits to GitHub repository pathto493/links_recommender
git push origin main
```

Once pushed:
1. Open **Streamlit Community Cloud** (`https://share.streamlit.io`).
2. Navigate to the app settings for `pathto493/links_recommender`.
3. In **Main file path**, update `streamlit_app.py` to:
   ```text
   server.py
   ```
4. Save and deploy.
5. In App Settings -> Secrets / Environment Variables, set `EAGLES_WING_ORIGIN` to your production frontend URL (e.g. `https://your-frontend-domain.com`) to allow browser CORS requests.
