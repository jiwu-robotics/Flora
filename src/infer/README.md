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

`dag/kestra/jiwu_flora.yaml` uses the standard
[Kestra Docker Task Runner](https://kestra.io/docs/task-runners/types/docker-task-runner)
with the host engine at `unix:///var/run/docker.sock`. Both tasks use the required `flora_image` input: a preloaded full image ID or
repository digest containing the current `/app/src/infer` and annotation programs.
An old image imported from another machine does not include local source changes. Commands run inside that image; no additional worker
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
| `/home/eisoc/data/debug_datapilot` | `/data/debug_datapilot` | Debug datasets and results |
| `/mnt/sdb/.datapilot-modelzoo` | `/model_zoo` | Prepared model cache, GPU task only |

Create the intended host directories with suitable permissions beforehand. A path
that exists only inside the Kestra container is not a host bind source. The flow
binds the model cache directly; no Compose cache override is required. Existing
results and model data remain in place; changing this example does not migrate or
remove any installation's data.

Set `dataset_dir` to a directory relative to the mount selected by `dataset`,
or to an absolute host path below the corresponding mount, `/mnt/sdb/datasets`,
or `/home/eisoc/data/debug_datapilot` (`~` is not expanded).
The workflow defaults to TempSeg GPU inference on all parts in the supplied UMI
directory. With `dagger` and `tempseg`, it reads Parquet directly in bounded parts without preparing AVI
files, reuses one model session, and prefetches at most one part across episodes on a reader thread. Set `inference`
to `false` for CPU validation only, select `dagger`, or set `max_parts` to a
positive value to limit the number of parts. Outputs are stored under
`<dataset_root>/temp_seg/runs/<execution-id>/validation/` and `inference/`, including
`manifest.json`. Every execution completes a separate full CPU preflight before
optional GPU inference. TempSeg defaults to `include_flags=true`; optional
`dataset_key` and `episodes` select its identity and episode inventory. Only complete
results with matching preflight identity and full frame coverage are handed off and
atomically copied to `<dataset_root>/temp_seg/results.json`. A bounded partial run
fails publication and leaves the previous successful canonical file intact. GPU runs
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
same dataset and parts. Results are stored under
`<dataset_root>/temp_seg/runs/<execution-id>/inference/`. Captioner prefers this
layout and falls back to the old `tempseg/<execution-id>/` layout for historical runs.
Build the current Flora image on the engine host when changing its code, then
supply its full image ID or repository digest as `flora_image`. The workflow uses
offline model loading and disables container networking; prepare all model assets
first. The writable model-cache mount permits Hugging Face lock files. Use the repository's normal image distribution procedure
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

## Native aggregate results (`flora_results_v1`)

`python -m src.infer --mode tempseg` now also writes `<output>/results.json`,
for direct Parquet, DAgger video preparation and UMI. Add `--dataset-key ID`
to echo the caller's dataset identifier; the default is the directory name.
This identifier does not prove ownership or source identity. Use `--episodes 9 19 29`
to select multiple, possibly nonconsecutive episodes in one aggregate. It is mutually
exclusive with `--episode`; missing or duplicate indices are rejected. Other model modes
retain their existing output interfaces.

```bash
# CPU validation; no model downloads or GPU inference.
python -m src.infer --kind dagger --mode tempseg --direct-parquet \
  --dataset /data/example --dataset-key example --episode 0 \
  --output /outputs/check-001
# After validation, use an independent output directory and approved resources.
python -m src.infer --kind dagger --mode tempseg --direct-parquet \
  --dataset /data/example --dataset-key example --episode 0 \
  --include-flags --run --output /outputs/run-001
```

The structural contract is [results.schema.json](results.schema.json).
Consumers read `results[dataset_key][chunk][episode_index]`. Each selected episode
is listed before processing, including those not reached by `--max-parts`.
`processed_ranges` describes successful model execution, independently of detected
segments. `complete` requires every selected episode to have full frame coverage;
empty detection can still be successful. Bounded runs can exit normally with
`partial` or `not_processed` results. CPU validation produces `validated` only for
fully checked episodes, empty segments/ranges and `complete=false`; an episode
only partly checked remains `not_processed`. Execution errors exit nonzero and,
when sufficient input identity is available, write a diagnostic `complete=false`
file with sanitized errors. Cancellation does not guarantee a result file.

Frames are original zero-based episode row indices with exclusive end bounds.
Seconds are relative to the first source presentation timestamp. The declared
`flora_frame_span_v1` rule retains Flora's covering-frame start and exclusive end;
concurrent overlapping segments remain separate. Optional flags use
`episode_boundaries_v1`: filter and merge boundaries across the whole episode,
not separately per part. Existing per-part flags keep their previous semantics.

UMI additionally requires its original Parquet from `meta/info.json`'s `data_path`.
Rows must have contiguous `frame_index`, matching `episode_index`, and a strictly
increasing `timestamp` (or `relative_timestamp_sec` when `timestamp` is absent).
Normalized row timestamps must match video PTS within one microsecond. Unsupported
clock mappings fail rather than falling back to FPS arithmetic. The DAgger AVI
path must pass the same clock check against its source rows; irregular DAgger
clocks should use `--direct-parquet` to retain native timestamps.

Source files and metadata use streamed SHA-256 digests and root-relative paths;
paths escaping the dataset are rejected. The producer revision is a content
SHA-256 of the adapter and annotation code, including pinned manifest/configuration.
Custom merged checkpoints are identified by a digest of their sorted relative
file names and SHA-256 digests, without claiming the default model revision.
Sources, code and model identity are checked again before publishing the file.
Results do not contain platform run IDs, credentials or absolute dataset paths.

Each attempt should have a separate writable output directory and read-only source
mount. Direct resume additionally requires the matching `results.identity.json`
written before execution, including all effective parameters and the full selected
source inventory. Old runs without this identity cannot be resumed under the new
contract. Resume removes the previous aggregate and rebuilds it from checked
per-part results; it cannot extend a run by changing `--max-parts`. Custom-weight
resume remains unsupported. Existing Captioner per-part reuse is preserved.

The aggregate is strict JSON, fsynced and atomically renamed in the output
directory. Files over 8 MiB fail explicitly; select fewer episodes instead of
truncating results. The final stdout line reports its path and `complete` value.
DataPilot ingestion, generic runner management and publication remain platform work;
this file alone does not authorize publication.
