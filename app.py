"""Hugging Face Spaces entry point for Voltic (Free ZeroGPU Tier).

Integrates the full Voltic analytics platform and dashboard with Hugging Face's
Gradio runtime and ZeroGPU supervisor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Ensure dataset and ML models exist before serving
model_file = ROOT / "trained_models" / "usage_model.pkl"
dataset_file = ROOT / "dataset" / "prepaid_meter_dataset.csv"

if not dataset_file.exists():
    print("[startup] Generating dataset...")
    from scripts.generate_dataset import main as gen_dataset
    gen_dataset()

if not model_file.exists():
    print("[startup] Training ML models...")
    from scripts.train_model import main as train_models
    train_models()

# ZeroGPU hook to satisfy Hugging Face ZeroGPU runtime requirement
try:
    import spaces  # type: ignore
    HAS_SPACES = True
except Exception:
    HAS_SPACES = False

if HAS_SPACES:
    @spaces.GPU
    def _voltic_gpu_worker(ping: str = "active") -> str:
        return f"Voltic GPU cluster online: {ping}"
else:
    def _voltic_gpu_worker(ping: str = "active") -> str:
        return f"Voltic engine online: {ping}"

try:
    import gradio as gr  # type: ignore
    HAS_GRADIO = True
except Exception:
    HAS_GRADIO = False

from app.config import settings
from app.database.db import init_db, seed_if_empty
from app.main import app as voltic_app

if HAS_GRADIO:
    # Initialize database explicitly when Gradio wraps routes (bypassing voltic_app lifespan)
    init_db()
    seed_if_empty()

    # Create Gradio demo with the @spaces.GPU dependency hooked to startup
    with gr.Blocks(title="Voltic — Prepaid Meter Analyzer") as demo:
        _hidden_in = gr.Textbox(value="startup", visible=False)
        _hidden_out = gr.Textbox(visible=False)
        demo.load(fn=_voltic_gpu_worker, inputs=_hidden_in, outputs=_hidden_out)

    # Build Gradio's native application
    app = gr.routes.App.create_app(demo)

    # Prepend all Voltic routes & static mounts so Voltic serves directly at root (/, /dashboard, /static, etc.)
    for r in voltic_app.routes:
        app.routes.insert(0, r)
else:
    app = voltic_app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)

