import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from src.infer.direct import atomic_json

root, artifacts = Path(sys.argv[1]), Path(sys.argv[2])
stage = os.environ["STAGE"]
mode = os.environ["MODEL_MODE"]
execution = os.environ["EXECUTION_ID"]
if not re.fullmatch(r"[a-zA-Z0-9_-]+", execution):
    raise ValueError("Invalid execution ID")
if not re.fullmatch(
    r"(?:sha256:|[^\s]+@sha256:)[0-9a-f]{64}", os.environ["FLORA_IMAGE"]
):
    raise ValueError(
        "flora_image must be a full local sha256 image ID or repository digest"
    )
help_text = subprocess.check_output(
    [sys.executable, "-m", "src.infer", "--help"], text=True
)
if not all(flag in help_text for flag in ("--dataset-key", "--episodes")):
    raise ValueError(
        "Selected image lacks native-results CLI support; rebuild it from current code"
    )
episodes = json.loads(os.environ["EPISODES_JSON"])
if (
    not isinstance(episodes, list)
    or any(type(i) is not int or i < 0 for i in episodes)
    or len(set(episodes)) != len(episodes)
):
    raise ValueError("episodes must contain distinct nonnegative integers")
key = os.environ["DATASET_KEY"]
if mode != "tempseg" and (episodes or key):
    raise ValueError("dataset_key and episodes require TempSeg mode")
run = root / "temp_seg" / "runs" / execution
output = run / ("validation" if stage == "validate" else "inference")
if not output.resolve().is_relative_to(root):
    raise ValueError("Output path escapes dataset root")
command = [
    sys.executable,
    "-m",
    "src.infer",
    "--kind",
    os.environ["DATASET_KIND"],
    "--dataset",
    str(root),
    "--mode",
    mode,
    "--max-parts",
    "0" if stage == "validate" else os.environ["MAX_PARTS"],
    "--output",
    str(output),
]
if mode == "tempseg":
    if os.environ["DATASET_KIND"] == "dagger":
        command += ["--direct-parquet"]
    if os.environ["INCLUDE_FLAGS"] == "true":
        command += ["--include-flags"]
    if key:
        command += ["--dataset-key", key]
    if episodes:
        command += ["--episodes", *map(str, episodes)]
if mode == "captioner":
    previous = os.environ["SEGMENTS_EXECUTION_ID"]
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", previous):
        raise ValueError("A valid segments_execution_id is required for Captioner")
    candidates = [
        root / "temp_seg" / "runs" / previous / "inference",
        root / "tempseg" / previous,
    ]
    prior = next((path for path in candidates if path.is_dir()), None)
    if prior is None or not prior.resolve().is_relative_to(root):
        raise ValueError("No matching prior TempSeg execution inside this dataset")
    if stage != "validate":
        command += ["--segments-dir", str(prior)]
if stage != "validate":
    if not (run / "validation" / "manifest.json").is_file():
        raise ValueError("Independent input validation must finish first")
    command += ["--run"]
warning_prefixes = (
    "[transformers] The `use_fast` parameter is deprecated",
    "[transformers] Kwargs passed to `processor.__call__`",
    "[transformers] Qwen3VL video processing does not apply",
    "[transformers] `causal_conv1d_fn` is falling back",
    "[transformers] `chunk_gated_delta_rule` is falling back",
    "[transformers] `causal_conv1d_update` is falling back",
    "[transformers] `fused_recurrent_gated_delta_rule` is falling back",
)
progress = re.compile(
    r"^(?:Fetching \d+ files:|Loading weights:|\d+% (?:Finding actions|Loading the action segmenter|Stitching finished|Writing captions))"
)
warning_context = False
process = subprocess.Popen(command, stderr=subprocess.PIPE, text=True, bufsize=1)
assert process.stderr is not None
for line in process.stderr:
    stripped = line.strip()
    known_warning = stripped.startswith(warning_prefixes) or (
        "peft/mapping_func.py:" in stripped and "UserWarning:" in stripped
    )
    continuation = warning_context and stripped == "warnings.warn("
    target = (
        sys.stdout
        if known_warning or continuation or progress.match(stripped)
        else sys.stderr
    )
    print(line, end="", file=target, flush=True)
    warning_context = known_warning
if process.wait():
    raise SystemExit(process.returncode)

artifacts.mkdir(parents=True, exist_ok=True)
shutil.copyfile(output / "manifest.json", artifacts / "manifest.json")
if mode == "tempseg":
    document = json.loads((output / "results.json").read_text())
    if stage == "validate":
        shutil.copyfile(output / "results.json", artifacts / "validation.json")
    else:
        # Bounded inference may exit zero with a partial result. Never publish it.
        if (
            document.get("schema_version") != "flora_results_v1"
            or document.get("complete") is not True
        ):
            raise ValueError(
                "TempSeg result is incomplete; archived diagnostics retained, canonical result unchanged"
            )
        checked = json.loads((run / "validation" / "results.json").read_text())
        if (
            document["selection"] != checked["selection"]
            or document["producer"] != checked["producer"]
        ):
            raise ValueError("Selection or producer changed since preflight")
        expected = {
            (e["chunk"], str(e["episode_index"]))
            for e in document["selection"]["episodes"]
        }
        rows = document["results"][document["selection"]["dataset_key"]]
        actual = {(chunk, index) for chunk, values in rows.items() for index in values}
        if actual != expected:
            raise ValueError("Result does not cover the selected episode inventory")
        for chunk, index in expected:
            row = rows[chunk][index]
            prior = checked["results"][document["selection"]["dataset_key"]][chunk][
                index
            ]
            if prior["status"] != "validated" or row["source"] != prior["source"]:
                raise ValueError("Episode source differs from validated input")
            if row["status"] != "success" or row["processed_ranges"] != [
                {"start_frame": 0, "end_frame": row["frame_count"]}
            ]:
                raise ValueError("Episode lacks full successful model coverage")
        shutil.copyfile(output / "results.json", artifacts / "results.json")
        canonical = root / "temp_seg" / "results.json"
        if not canonical.resolve().is_relative_to(root):
            raise ValueError("Canonical result escapes dataset root")
        atomic_json(canonical, document)
else:
    for part in output.glob("episode_*.json"):
        shutil.copyfile(part, artifacts / ("part-" + part.name))
