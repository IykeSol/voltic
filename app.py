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

import gradio as gr
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database.db import init_db, seed_if_empty
from app.main import app as voltic_app

# Initialize database
init_db()
seed_if_empty()

# Custom CSS to make the dashboard full-bleed without padding
custom_css = """
.gradio-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
footer { display: none !important; }
"""

with gr.Blocks(title="Voltic — Prepaid Meter Analyzer", fill_width=True) as demo:
    # Hidden components that trigger the @spaces.GPU worker during app startup
    _hidden_in = gr.Textbox(value="startup", visible=False)
    _hidden_out = gr.Textbox(visible=False)
    demo.load(fn=_voltic_gpu_worker, inputs=_hidden_in, outputs=_hidden_out)

    # Embed the full interactive Voltic Dashboard
    gr.HTML(
        """
        <iframe src="/dashboard" style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; border: none; margin: 0; padding: 0; z-index: 9999;"></iframe>
        """
    )

# Attach all Voltic FastAPI routes onto demo.app cleanly
demo.app.include_router(voltic_app.router)

# Mount static files directly on demo.app
demo.app.mount("/static", StaticFiles(directory=settings.FRONTEND_DIR), name="static")

if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7860,
        ssr_mode=False,
    )

