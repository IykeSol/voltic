"""Hugging Face Spaces entry point for Voltic (Free Gradio / ZeroGPU Tier).

Serves the full Voltic application on port 7860, including the interactive
dashboard, machine-learning forecasting engine, and Gemini AI insights.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ZeroGPU hook to satisfy Hugging Face ZeroGPU runtime requirement
try:
    import spaces
    gpu_decorator = spaces.GPU
except Exception:
    def gpu_decorator(fn):
        return fn


@gpu_decorator
def _voltic_gpu_worker(ping: str = "active") -> str:
    """ZeroGPU worker stub so Hugging Face assigns runtime slice."""
    return f"Voltic engine online: {ping}"


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

# Minimal Gradio interface connected to the @spaces.GPU function
demo = gr.Interface(
    fn=_voltic_gpu_worker,
    inputs=gr.Textbox(label="Status", value="active"),
    outputs=gr.Textbox(label="Result"),
    title="⚡ Voltic AI Engine",
    description="Your dashboard is running! Navigate to [**Dashboard**](/) to view the application.",
)

# Mount Gradio at /gradio with ssr_mode=False to avoid secondary Node.js port conflicts
app = gr.mount_gradio_app(app, demo, path="/gradio", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
