# Jiwu dataset adapter

This adapter reads LeRobot v2.1 metadata. `dagger` selects
`observation.images.high_cam` (JPEG bytes in Parquet) and uses Flora's `yam`
profile; `umi` selects the native `observation.images.ego_l` MP4 and uses
`human`. No wrist views are supplied. Episodes are identified using
`meta/episodes.jsonl`, `meta/info.json` and their path templates.

DAgger JPEGs are copied into 60-second-or-smaller MJPEG AVI files without
re-encoding, at the dataset's declared frame rate. Each part records its
starting frame and episode-relative offset in `manifest.json`. Outputs from
inference have their segment times adjusted to episode-relative seconds, and
include `episode_source`. The adapter checks episode frame counts, missing
frames and Flora input constraints. Incomplete segment statuses cause an
error. UMI videos are passed through unchanged; oversized or otherwise invalid
videos are reported by Flora rather than silently modified.

The default mode only performs CPU input validation. Each invocation writes
its manifest, any prepared media, and inference results (when `--run` is used)
to a new `<dataset>/flora_annotations/<run-id>/` directory. For example, mount
the dataset writable and run:

```sh
docker run --rm -v /mnt/sdb/jiwu-umi:/data \
  jiwu.robotics/robox-datapilot/flora:latest \
  python -m src.infer --kind umi \
  --dataset /data/Robot_data_Bing_20261111_144059 \
  --max-parts 1
```

Use `--kind dagger` with the DAgger path for the head camera. `--episode N`
selects an episode; `--max-parts 0` (the default for the CLI) processes all
parts. Use `--output` to select a different output directory; it must not
contain an existing manifest. Add `--run`, GPU access and
model-cache mounts for actual annotation; input validation is always run first.
The GPU run requires the hardware and cache described in the repository
`AGENTS.md`. Weight downloads to a new disk require prior approval.

## Local Kestra

`kestra/jiwu_flora.yaml` targets the DataPilot Kestra Docker-in-Docker runner on
this host. The runner needs the image imported into its own Docker daemon; its
`/data/jiwu-dagger` and `/data/jiwu-umi` mounts may be read-only; outputs go to the writable results volume.
The Docker-in-Docker runner binds `/mnt/sdb/.datapilot-modelzoo` to `/model_zoo` using `kestra/docker-compose.modelzoo.yml`; the GPU task uses this mount for model weights. Include this override with the DataPilot Compose files when recreating the runner. To roll back, recreate the runner without the override and remove the `/model_zoo` task volume and environment overrides from the flow. The
workflow defaults to validating one UMI part on CPU;
select `dagger`, set `max_parts` to `0` for all, or set `inference` to `true`
for GPU inference after arranging an approved cache and suitable GPU. Outputs
are stored under `/var/lib/preprocess-results/flora-annotations/<dataset>/<execution-id>`. The GPU task's
cache is at `/model_zoo` in the container, backed by `/mnt/sdb/.datapilot-modelzoo` on the host.

## Model selection

With `--run`, `--mode both` (the default) runs TempSeg followed by Captioner;
`--mode tempseg` runs segmentation only. To run just Captioner, supply
`--mode captioner --segments-dir /path/to/tempseg/run`. The directory must
contain the matching TempSeg results for every selected part. The adapter
checks episode metadata, video hashes and profile before using those intervals;
TempSeg times are converted back from episode-relative to part-relative time.
Without `--run`, only input validation is performed.

In Kestra, select `model_mode` and set `inference=true`. For `captioner`, set
`segments_execution_id` to a previous successful TempSeg execution for the
same dataset and parts. Results are stored on the results volume at
`/var/lib/preprocess-results/flora-annotations/<dataset>/<execution-id>`.
The flow uses `jiwu.robotics/robox-datapilot/flora:latest`. Build it in the runner's Docker
daemon using the existing Dockerfile after changing the code:

```sh
tar --exclude=__pycache__ --exclude='*.pyc' -cf - \
  docker/Dockerfile.ubuntu24.04-2.11.0+cu128 docker/download_tempseg.py \
  captioner src requirements LICENSE | \
  docker exec -i robox-datapilot-datapilot-preprocess-dind-1 \
    sh -c 'DOCKER_HOST=tcp://localhost:2375 docker build -f docker/Dockerfile.ubuntu24.04-2.11.0+cu128 -t jiwu.robotics/robox-datapilot/flora:latest -'
```

GPU inference still requires approval before downloading weights to a new disk.

### Direct Parquet TempSeg input

The TempSeg entry point can read embedded `observation.images.high_cam` JPEGs
without exporting a video. Use `--image-key observation.images.front_cam` to
select a different JPEG column; the default is `observation.images.high_cam`.
The same option is available in `src.infer` for dagger datasets.
Validate an episode first:

```bash
python captioner/tempseg_infer.py --dataset-path /path/to/dataset \
  --episode-index 0 --validate-only
```

Then run with a local merged checkpoint, or omit `--weights-path` to use the
existing pinned base-model and adapter loading path:

```bash
python captioner/tempseg_infer.py --dataset-path /path/to/dataset \
  --episode-index 0 --weights-path /path/to/merged-qwen3.5-9b \
  --include-flags --flag-merge-gap 30 --output-dir outputs/tempseg
```

Omit `--episode-index` to process all episodes in one process with a shared model.
The dataset profile defaults to `yam`; video and JSONL defaults remain unchanged.
The package-handling instruction is an optional example at
`captioner/examples/package_phases.txt`; pass its contents through `--instruction`
when that task applies. There is no hardcoded task instruction.

The reader uses `meta/info.json` (`fps`, and when present `data_path` and
`chunks_size`) plus `meta/episodes.jsonl`. For datasets without the episode
manifest/path template, it discovers `data/chunk-*/episode_*.parquet`.
Files must contain one episode with contiguous zero-based `frame_index`, strictly
increasing `relative_timestamp_sec`, and valid JPEG bytes. The native limits
remain 120 seconds, 7200 frames, at most 4096 pixels per side, and at least 4 FPS.
The total encoded JPEG payload is limited to 256 MiB. Oversized episodes are
rejected; this direct path does not silently split or resample them.

Results retain `flora_tempseg_v1`, seconds, metadata, provenance and input hashes.
Each segment also contains `start_frame` and exclusive `end_frame`. Optional
`flags` exclude boundaries below frame 10 and at/above `frame_count - 10`, then
merge successive gaps strictly smaller than `--flag-merge-gap` and round each
group mean. A gap of zero disables merging. Frames are native sequence positions,
not indices into the model's 4 FPS sample. Parquet outputs carry `input_type` and
`dataset_source`; the existing video-only `caption_only.py` cannot consume them.
Existing outputs require `--overwrite` to replace.

The dataset adapter also exposes this path explicitly:

```bash
python -m src.infer --dataset /path/to/dataset --kind dagger --mode tempseg \
  --direct-parquet --episode 0 --output outputs/direct-check
```

Add `--run` for inference after its automatic CPU validation. `--weights-path`,
`--instruction`, `--include-flags`, and `--flag-merge-gap` are forwarded in TempSeg
mode. The adapter starts a separate process per episode; use the direct
`captioner/tempseg_infer.py` batch command above for model reuse. Other adapter
modes keep their existing video preparation behavior.
