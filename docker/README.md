# Flora TempSeg container

Build and publish the image (registry authentication is required for push):

```bash
docker compose build
docker compose push
```

The image contains the annotation pipeline; the example below runs only TempSeg and produces action intervals without captions. Download its pinned adapter and Qwen base model before inference:

```bash
docker compose run --rm flora python docker/download_tempseg.py
```

The adapter goes to `./model_zoo/flora/models` and the base model to `./model_zoo/huggingface`. Both are mounted into the container and excluded from the image and Git. The download validates the adapter manifest; interrupted downloads can be resumed by running the command again. Set `HF_TOKEN` in the environment if needed; do not place it in a command or repository. Downloading weights to a new disk requires prior approval under AGENTS.md. The full TempSeg → Captioner pipeline additionally downloads Captioner weights into the same mounted cache.

Mount the input directory with `FLORA_DATA_DIR` and use `FLORA_OUTPUT_DIR` for a writable output directory. For the supplied example:

```bash
export FLORA_DATA_DIR=/mnt/sdb/datasets/UMI_data/Robot_data_zf_20261104_212558/videos/chunk-000/observation.images.ego_l
export FLORA_OUTPUT_DIR="$PWD/outputs"
docker compose run --rm flora python captioner/tempseg_infer.py --video /data/episode_000002.mp4 --profile human --validate-only
# After validation, on a suitable GPU:
docker compose run --rm flora python captioner/tempseg_infer.py --video /data/episode_000002.mp4 --profile human --output /outputs/episode_000002.json
```

Choose `human`, `yam`, `dex`, or `tianji` to match the video; the example uses the single-camera human profile and does not establish the subject type. The JSON result contains `segments` with `start_s`, `end_s`, and `segmentation_provenance`, plus input hashes and model revisions. Segments can overlap. See `--help` for three-camera and JSONL inputs, `--include-audit`, and overwrite behavior. The upstream pipeline was validated on an 80 GB NVIDIA GPU; see the repository README and model guides for input constraints and license terms.

For timestamped captions instead, replace `captioner/tempseg_infer.py` with `captioner/infer.py` in the commands above. Rewarder uses incompatible dependencies and needs its own environment; it is not installed in this image.

## Make targets

Run `make` or `make help` from the repository root to list the available
commands. `make image` builds the Compose image and `make image-push` pushes
it; pushing requires registry access. Pass Compose build options with, for
example, `make image BUILD_OPTIONS='--no-cache'`.

`make test` runs the adapter's CPU-only unit tests. `make lint`, `make format`,
`make format-check`, and `make check` use [Ruff](https://docs.astral.sh/ruff/).
Install Ruff in a separate tools environment or make it available on `PATH`;
set `RUFF=/path/to/ruff` to choose an executable. These targets cover
`src/infer`, `tests`, and the Docker Python helpers by default; set
`PYTHON_PATHS` to select other paths. Vendor directories are excluded. The
annotation and Rewarder environments remain separate.
