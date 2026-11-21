# Eagles Wing ML Recommendation Lab

A separate Python + Streamlit recommendation project. Does **not** modify Eagles Wing.

## macOS setup

```bash
cd eagles-wing-ml-starter
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python build_index.py --csv "$HOME/Downloads/YoutubeLinksWithInfo - Sheet1.csv" --device cpu
streamlit run server.py
```

`--device mps` is optional after confirming `torch.backends.mps.is_available()`; CPU is fine for 1,225 titles.

Browse http://localhost:8501 and test the API:

```bash
curl -s http://localhost:8501/health
curl -s -X POST http://localhost:8501/recommend \
  -H 'Content-Type: application/json' \
  -d '{"text":"I am discouraged about my future","top_k":3}'
```

## Deployment

1. Commit `server.py`, `ui.py`, `engine.py`, `requirements.txt`, and all three `artifacts/` files to a dedicated GitHub repository. Never commit `.venv/` or private reflection text.
2. Deploy entrypoint `server.py` in Streamlit Community Cloud. Free hosting sleeps when unused; custom route and CORS must be confirmed on the deployed URL before connecting Eagles Wing.
3. Set `EAGLES_WING_ORIGIN` to the exact existing frontend HTTPS origin in the Community Cloud app's environment if supported. If environment variables are unavailable, supply the origin through Streamlit secrets/code with appropriate review. Check the CORS header from a browser.
4. Verify the `/health` and `/recommend` endpoints on the deployed URL. If custom routes are not reachable on that host, keep these model artifacts and serve `engine.recommend` through FastAPI on a compatible HTTP host instead.
5. Add an Eagles Wing feature that calls the endpoint and matches `video_id` against its live Google Sheets records. Do not modify existing playback or history-save semantics.

**Model note:** `build_index.py` computes embeddings with a pretrained model. It does not fine-tune neural weights. Fine-tuning requires labeled examples of user reflections and relevant/irrelevant videos. The cloud service will download/load the same model on startup, so it still needs connectivity and RAM.

**Catalog note:** The model index is based on a CSV snapshot. New or changed Google Sheets titles need a rebuild/redeploy before semantic search includes them. React must ignore video IDs no longer present in the live sheet.

**Security note:** This public endpoint has no authentication/rate limiter and is suitable for a limited personal MVP only. CORS is not security or abuse protection. Add real abuse controls for broader public use.
# links_recommender
