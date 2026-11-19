"""Prepare Jiwu camera data and run Flora with episode-relative timestamps."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid
from contextlib import closing

from .direct import atomic_json
from .prefetch import prefetch_parts

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 240 * 1024 * 1024


def rows(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def source_path(root, template, episode, chunks_size, **extra):
    path = (
        root
        / template.format(
            episode_chunk=episode // chunks_size, episode_index=episode, **extra
        )
    ).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError(f"dataset path escapes root: {path}")
    return path


def dataset(root, kind, selected, image_key=None):
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
    fps, chunk = info["fps"], info["chunks_size"]
    if (
        not isinstance(fps, (int, float))
        or fps < 4
        or not isinstance(chunk, int)
        or chunk < 1
    ):
        raise ValueError("Invalid fps or chunk size in dataset metadata")
    episodes = list(rows(root / "meta/episodes.jsonl"))
    ids = [x["episode_index"] for x in episodes]
    if len(set(ids)) != len(ids) or any(not isinstance(x, int) or x < 0 for x in ids):
        raise ValueError("Invalid or duplicate episode index")
    if selected is not None:
        episodes = [x for x in episodes if x["episode_index"] == selected]
    if not episodes:
        raise ValueError("No matching episodes")
    key = (
        (image_key or "observation.images.high_cam")
        if kind == "dagger"
        else "observation.images.ego_l"
    )
    expected = "image" if kind == "dagger" else "video"
    if info.get("features", {}).get(key, {}).get("dtype") != expected:
        raise ValueError(f"Expected {key} feature of dtype {expected}")
    for ep in episodes:
        index = ep["episode_index"]
        if kind == "dagger":
            path = source_path(root, info["data_path"], index, chunk)
        else:
            path = source_path(root, info["video_path"], index, chunk, video_key=key)
        yield ep, path, fps, key


def dagger_parts(path, episode, fps, key, out, max_parts):
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    if key not in parquet.schema_arrow.names:
        raise ValueError(f"Missing {key} in {path}")
    if parquet.metadata.num_rows != episode["length"]:
        raise ValueError("Parquet frame count differs from episode metadata")
    max_frames = int(fps * 60)
    process = None
    count = size = start = part = 0
    target = None

    def finish():
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError(f"ffmpeg failed while writing {target}")
        if count < 2:
            raise ValueError(f"Chunk {target} has fewer than two frames")
        return {
            "id": f"episode_{episode['episode_index']:06d}_part_{part:04d}",
            "video": str(target),
            "start_frame": start,
            "frames": count,
            "offset_s": start / fps,
        }

    try:
        for batch in parquet.iter_batches(batch_size=64, columns=[key, "frame_index"]):
            images = batch.column(0).to_pylist()
            indices = batch.column(1).to_pylist()
            for image, index in zip(images, indices, strict=True):
                if index != start + count:
                    raise ValueError(
                        f"Unexpected frame_index {index}; expected {start + count}"
                    )
                payload = image.get("bytes") if isinstance(image, dict) else None
                if not payload or not payload.startswith(b"\xff\xd8"):
                    raise ValueError(f"Missing or non-JPEG frame {index}")
                if process and (
                    count >= max_frames
                    or (size + len(payload) > MAX_BYTES and count >= 2)
                ):
                    yield finish()
                    process = None
                    part += 1
                    start += count
                    count = size = 0
                    if max_parts and part >= max_parts:
                        return
                if process is None:
                    target = (
                        out
                        / f"episode_{episode['episode_index']:06d}_part_{part:04d}.avi"
                    )
                    if target.exists():
                        raise FileExistsError(target)
                    process = subprocess.Popen(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-f",
                            "image2pipe",
                            "-framerate",
                            str(fps),
                            "-vcodec",
                            "mjpeg",
                            "-i",
                            "pipe:0",
                            "-c:v",
                            "copy",
                            "-f",
                            "avi",
                            str(target),
                        ],
                        stdin=subprocess.PIPE,
                    )
                process.stdin.write(payload)
                count += 1
                size += len(payload)
        if process:
            yield finish()
            process = None
    finally:
        if process and process.poll() is None:
            process.stdin.close()
            process.wait()


def prepare_video_parts(args, root, mode, media, image_key):
    """Prepare and validate inputs in the background, preserving dataset order."""
    from batch_utils.api import DataEnginePipeline
    from batch_utils.config import MODELS

    profile = "yam" if args.kind == "dagger" else "human"
    instruction = getattr(args, "instruction", "")
    produced = 0
    for episode, path, fps, key in dataset(
        root, args.kind, args.episode, image_key=image_key
    ):
        remaining = args.max_parts - produced if args.max_parts else 0
        if args.kind == "dagger":
            parts = dagger_parts(path, episode, fps, key, media, remaining)
        else:
            parts = iter(
                [
                    {
                        "id": f"episode_{episode['episode_index']:06d}",
                        "video": str(path),
                        "start_frame": 0,
                        "frames": episode["length"],
                        "offset_s": 0,
                    }
                ]
            )
        try:
            for part in parts:
                job = {
                    **part,
                    "episode_index": episode["episode_index"],
                    "fps": fps,
                    "camera": key,
                    "source": str(path),
                }
                videos, canonical = DataEnginePipeline._inputs(
                    part["video"], profile=profile, instruction=instruction
                )
                inspection = DataEnginePipeline._inspection(videos, canonical)
                if mode == "tempseg":
                    inspection.update(
                        input_type="video",
                        model_revisions={
                            name: MODELS[name] for name in ("tempseg", "tempseg_base")
                        },
                    )
                print(json.dumps(inspection, allow_nan=False), flush=True)
                if args.kind == "umi" and inspection["duration_s"] > 90:
                    raise ValueError(f"{path}: UMI episode exceeds 90 seconds")
                if inspection["cameras"]["main"]["frames"] != part["frames"]:
                    raise ValueError(
                        f"{path}: decoded frame count differs from episode metadata"
                    )
                produced += 1
                yield job, videos, canonical, inspection
                if args.max_parts and produced >= args.max_parts:
                    return
        finally:
            close = getattr(parts, "close", None)
            if close is not None:
                close()


def read_segments(directory, job):
    source = json.loads((directory / (job["id"] + ".json")).read_text(encoding="utf-8"))
    prior = source.get("episode_source", {})
    for key in ("episode_index", "start_frame", "frames", "fps", "camera", "source"):
        if prior.get(key) != job[key]:
            raise ValueError(f"Segment source mismatch for {job['id']}: {key}")
    if source.get("segment_coordinates") != "part":
        for segment in source["segments"]:
            segment["start_s"] -= job["offset_s"]
            segment["end_s"] -= job["offset_s"]
    return source


def write_episode_result(output, job, result, *, captions):
    from batch_utils.cli import write_result

    for segment in result["segments"]:
        segment["start_s"] += job["offset_s"]
        segment["end_s"] += job["offset_s"]
        for key in ("start_frame", "end_frame"):
            if key in segment:
                segment[key] += job["start_frame"]
    if "flags" in result:
        result["flags"] = [flag + job["start_frame"] for flag in result["flags"]]
    result["episode_source"] = {
        key: value for key, value in job.items() if key != "video"
    }
    path = output / (job["id"] + ".json")
    write_result(path, result)
    if captions:
        incomplete = sum(s.get("status") != "complete" for s in result["segments"])
        if incomplete:
            raise ValueError(f"{path}: {incomplete} incomplete segments")


def run_video_stages(args, mode, output, prepared):
    import torch
    from batch_utils.api import DataEnginePipeline, checked_annotation
    from batch_utils.cli import progress
    from batch_utils.models import Session
    from batch_utils.pipeline import caption_annotation, segment_annotation
    from caption_only import caption_result
    from tempseg_infer import segment_result

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for inference.")
    entries = []
    instruction = getattr(args, "instruction", "")
    if mode == "both":
        checkpoints = output / "segments"
        checkpoints.mkdir()
    with closing(
        Session(tempseg_weights_path=getattr(args, "weights_path", None))
    ) as session:
        for job, videos, profile, inspection in prepared:
            path = output / (job["id"] + ".json")
            if path.exists():
                raise FileExistsError(path)
            if mode == "captioner":
                source = read_segments(args.segments_dir, job)
                result = caption_result(
                    videos, profile, source, inspection, session, progress
                )
                write_episode_result(output, job, result, captions=True)
            else:
                segmentation = segment_annotation(
                    videos, profile, False, instruction, progress, session
                )
                result = segment_result(
                    videos,
                    profile,
                    segmentation["segments"],
                    segmentation["elapsed_s"],
                    flag_merge_gap=(
                        args.flag_merge_gap
                        if getattr(args, "include_flags", False)
                        else None
                    ),
                )
                if mode == "both":
                    result["segment_coordinates"] = "part"
                    result["episode_source"] = {
                        key: value for key, value in job.items() if key != "video"
                    }
                    atomic_json(checkpoints / path.name, result)
                else:
                    write_episode_result(output, job, result, captions=False)
            entries.append(job)

    if mode == "both":

        def prepare_captions():
            profile = "yam" if args.kind == "dagger" else "human"
            for job in entries:
                source = read_segments(checkpoints, job)
                videos, canonical = DataEnginePipeline._inputs(
                    job["video"], profile=profile
                )
                yield job, videos, canonical, source

        with (
            closing(prefetch_parts(prepare_captions())) as parts,
            closing(Session()) as session,
        ):
            for job, videos, profile, source in parts:
                result = caption_annotation(
                    videos, profile, source, instruction, progress, session
                )
                checked_annotation(result, include_audit=False)
                write_episode_result(output, job, result, captions=True)
    return entries


def run(args):
    root = args.dataset.resolve(strict=True)
    output = (
        args.output
        if args.output is not None
        else root / "flora_annotations" / uuid.uuid4().hex
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.json"
    if manifest.exists() and not getattr(args, "resume", False):
        raise FileExistsError(manifest)
    media = output / "media"
    media.mkdir(exist_ok=True)
    mode = getattr(args, "mode", "both")
    segments_dir = getattr(args, "segments_dir", None)
    if args.run and mode == "captioner" and segments_dir is None:
        raise ValueError("--segments-dir is required for captioner mode")
    direct = getattr(args, "direct_parquet", False)
    if direct and (args.kind != "dagger" or mode != "tempseg"):
        raise ValueError("--direct-parquet requires --kind dagger --mode tempseg")
    if mode != "tempseg" and (
        getattr(args, "weights_path", None)
        or getattr(args, "include_flags", False)
        or getattr(args, "instruction", "")
    ):
        raise ValueError(
            "--weights-path, --include-flags and --instruction require --mode tempseg"
        )
    image_key = getattr(args, "image_key", None)
    if image_key is not None and (args.kind != "dagger" or not image_key.strip()):
        raise ValueError(
            "--image-key requires --kind dagger and a nonempty column name"
        )
    if direct:
        from .direct import run_direct

        return run_direct(
            args,
            root,
            output,
            dataset(root, args.kind, args.episode, image_key=image_key),
        )
    captioner = str(ROOT / "captioner")
    if captioner not in sys.path:
        sys.path.insert(0, captioner)
    with closing(
        prefetch_parts(
            prepare_video_parts(args, root, mode, media, image_key),
            limit=args.max_parts,
        )
    ) as parts:
        entries = (
            run_video_stages(args, mode, output, parts)
            if args.run
            else [job for job, *_ in parts]
        )

    manifest.write_text(
        json.dumps(
            {
                "dataset": str(root),
                "kind": args.kind,
                "validated": True,
                "inference": args.run,
                "mode": mode if args.run else "validate",
                "parts": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(manifest),
                "validated_parts": len(entries),
                "inference": args.run,
            }
        ),
        flush=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--kind", choices=("dagger", "umi"), required=True)
    p.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: a new directory under DATASET/flora_annotations)",
    )
    p.add_argument("--episode", type=int)
    p.add_argument(
        "--max-parts", type=int, default=0, help="Maximum parts to process, 0 means all"
    )
    p.add_argument(
        "--run", action="store_true", help="Run GPU inference after CPU validation"
    )
    p.add_argument(
        "--mode",
        choices=("both", "tempseg", "captioner"),
        default="both",
        help="Models to run with --run",
    )
    p.add_argument(
        "--segments-dir",
        type=Path,
        help="TempSeg output directory required for captioner mode",
    )
    p.add_argument(
        "--direct-parquet",
        action="store_true",
        help="Read embedded JPEGs in bounded parts for dagger TempSeg.",
    )
    p.add_argument(
        "--weights-path", type=Path, help="Local merged checkpoint for TempSeg mode."
    )
    p.add_argument(
        "--include-flags",
        action="store_true",
        help="Include frame boundaries in TempSeg output.",
    )
    p.add_argument("--flag-merge-gap", type=int, default=30)
    p.add_argument(
        "--instruction", default="", help="Optional task instruction for TempSeg mode."
    )
    p.add_argument(
        "--image-key",
        help="JPEG column for dagger datasets (default: observation.images.high_cam).",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Resume matching direct Parquet results in the same output directory.",
    )
    args = p.parse_args()
    if args.resume and (not args.direct_parquet or not args.run or args.output is None):
        p.error("--resume requires --direct-parquet --run and --output")
    if args.flag_merge_gap < 0:
        p.error("--flag-merge-gap must be nonnegative")
    if args.segments_dir and (not args.run or args.mode != "captioner"):
        p.error("--segments-dir requires --run --mode captioner")
    if args.run and args.mode == "captioner" and not args.segments_dir:
        p.error("--run --mode captioner requires --segments-dir")
    if args.max_parts < 0 or (args.episode is not None and args.episode < 0):
        p.error("episode and max-parts must be non-negative")
    try:
        run(args)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(f"Jiwu inference failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
