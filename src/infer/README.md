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
frames and Flora input constraints. All dataset modes prepare and validate at
most one upcoming part in the background while inference runs serially. Every
dataset mode reuses one model session per stage across all parts. Incomplete
segment statuses cause an error. UMI videos are passed through unchanged; oversized or otherwise invalid
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

`kestra/jiwu_flora.yaml` uses the standard
[Kestra Docker Task Runner](https://kestra.io/docs/task-runners/types/docker-task-runner)
with the host engine at `unix:///var/run/docker.sock`. Both tasks use the existing
`jiwu.robotics/robox-datapilot/flora:latest` image, which contains `/app/src/infer`
and the annotation programs. Commands run inside that image; no additional worker
image or container-launch script is needed.

The trusted Kestra worker needs access to the host socket and Docker runner
`volume-enabled: true`. Task containers receive no Docker socket. The GPU task
requires the host NVIDIA container runtime. With `pullPolicy: NEVER`, prepare the
Flora image in that same host engine before running the flow.

Every volume source is a path on the engine host. Adapt the example's source
paths to the installation before deployment:

| Host source | Task path | Access |
| --- | --- | --- |
| `/mnt/sdb/jiwu-dagger` | `/data/jiwu-dagger` | Dataset and results |
| `/mnt/sdb/jiwu-umi` | `/data/jiwu-umi` | Dataset and results |
| `/mnt/sdb/datasets` | `/data/datasets` | Standard datasets and results |
| `/mnt/sdb/.datapilot-modelzoo` | `/model_zoo` | Prepared model cache, GPU task only |

Create the intended host directories with suitable permissions beforehand. A path
that exists only inside the Kestra container is not a host bind source. The flow
binds the model cache directly; no Compose cache override is required. Existing
results and model data remain in place; changing this example does not migrate or
remove any installation's data.

Set `dataset_dir` to a directory relative to the mount selected by `dataset`,
or to an absolute host path below the corresponding mount or `/mnt/sdb/datasets`.
The workflow defaults to TempSeg GPU inference on all parts in the supplied UMI
directory. With `dagger` and `tempseg`, it reads Parquet directly in bounded parts without preparing AVI
files, reuses one model session, and prefetches at most one part across episodes on a reader thread. Set `inference`
to `false` for CPU validation only, select `dagger`, or set `max_parts` to a
positive value to limit the number of parts. Outputs are stored under
`<dataset_root>/tempseg/<execution-id>/`, including `manifest.json`. GPU runs
require a suitable GPU and an approved model cache.

## Model selection

With `--run`, `--mode both` (the default) runs TempSeg over all selected
parts, releases its model, then runs Captioner over all parts. Intermediate
TempSeg results keep part-relative coordinates under `<output>/segments/`.
After segmentation completes, that directory can be used with
`--mode captioner --segments-dir` and a new output directory.
`--mode tempseg` runs segmentation only. To run just Captioner, supply
`--mode captioner --segments-dir /path/to/tempseg/run`. The directory must
contain the matching TempSeg results for every selected part. The adapter
checks episode metadata, video hashes and profile before using those intervals;
Standalone TempSeg outputs are converted back from episode-relative to part-relative time.
Without `--run`, only input validation is performed.

In Kestra, select `model_mode` and set `inference=true`. For `captioner`, set
`segments_execution_id` to a previous successful TempSeg execution for the
same dataset and parts. Results are stored under `<dataset_root>/tempseg/<execution-id>/`.
Build the existing Flora image with `docker compose build` on the engine host
when changing its code. Use the repository's normal image distribution procedure
for another host; no separate nested image store is involved.

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
mode. The adapter reads ordered Parquet rows into bounded parts (at most 60 s
and 240 MiB of JPEG data), prefetches at most one part across episodes, and reuses one model session. Results are written per
part with episode-relative frame and time offsets; the manifest is written after
completion. Use `--resume --run --output <same-directory>` to reuse matching
completed parts. Resume is not supported with custom merged weights. Other
adapter modes keep their existing video preparation behavior.
