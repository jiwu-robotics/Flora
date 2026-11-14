"""Download the exact TempSeg assets used by the inference pipeline."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "captioner"))

from huggingface_hub import snapshot_download
from batch_utils.config import MODELS
from batch_utils.models import preflight_adapter_download


if __name__ == "__main__":
    preflight_adapter_download()
    spec = MODELS["tempseg_base"]
    path = snapshot_download(
        spec["repo"],
        revision=spec["revision"],
        token=os.environ.get("HF_TOKEN"),
        allow_patterns=["*.safetensors", "*.json", "*.jinja"],
    )
    print(f"TempSeg base model ready: {path}")
