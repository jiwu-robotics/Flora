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
`/data/jiwu-dagger` and `/data/jiwu-umi` mounts must be writable in both the
outer Docker-in-Docker service and its task container. The current local
DataPilot runner mounts these paths read-only, so its configuration must be
changed and the service recreated before this flow can write to the datasets.
The `/var/lib/preprocess-results` mount is used for the model cache. The
workflow defaults to validating one UMI part on CPU;
select `dagger`, set `max_parts` to `0` for all, or set `inference` to `true`
for GPU inference after arranging an approved cache and suitable GPU. Outputs
are stored under `<dataset>/flora_annotations/<execution-id>`. The GPU task's
cache is in the results volume under `flora-model-cache`; it is empty
unless populated separately, and running it can download model weights there.
