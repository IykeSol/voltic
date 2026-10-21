"""Hugging Face Spaces entry point for Voltic (Free Gradio Tier).

Serves the full Voltic application on port 7860, including the interactive
dashboard, machine-learning forecasting engine, and Gemini AI insights.
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

import gradio as gr
from app.main import app

# Minimal Gradio block for Hugging Face healthcheck
with gr.Blocks(title="Voltic API") as demo:
    gr.Markdown(
        """
        # ⚡ Voltic — Prepaid Meter Usage Analyzer
        
        The service is active and running!
        
        👉 **[Click here to open the Voltic Dashboard](/)**
        """
    )

# Mount Gradio at /gradio; all primary routes (/, /dashboard, /login, /static)
# are handled directly by Voltic's custom frontend.
app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
