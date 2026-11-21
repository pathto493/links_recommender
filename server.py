"""Streamlit app with isolated custom JSON REST endpoints."""
import os
import streamlit as st
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from engine import recommend

async def health(request):
    return JSONResponse({"status": "ok", "service": "eagles-wing-recommendations"})

async def recommendations(request):
    if request.headers.get("content-length") and int(request.headers["content-length"]) > 8192:
        return JSONResponse({"error": "request too large"}, status_code=413)
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse({"error": "JSON object required"}, status_code=400)
        return JSONResponse(recommend(payload.get("text"), payload.get("top_k", 5)))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "recommendation service unavailable"}, status_code=503)

# Local development allows localhost:3000. Set EAGLES_WING_ORIGIN to your
# production HTTPS origin when deploying. This controls browser CORS, not auth.
origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
if os.getenv("EAGLES_WING_ORIGIN"):
    origins.append(os.environ["EAGLES_WING_ORIGIN"].rstrip("/"))

app = st.App(
    "ui.py",
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/recommend", recommendations, methods=["POST"]),
    ],
    middleware=[Middleware(CORSMiddleware, allow_origins=origins,
                           allow_methods=["GET", "POST", "OPTIONS"],
                           allow_headers=["Content-Type"])],
)
