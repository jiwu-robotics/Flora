"""Bounded Parquet TempSeg execution with a single reusable model session."""

import hashlib
import json
import os
import resource
import sys
import time
import tempfile
from pathlib import Path
from contextlib import ExitStack, closing

from .prefetch import prefetch_parts


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix=".flora-", dir=path.parent)
    try:
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def iter_dataset_parts(root, episodes, reader):
    """Read and hash episodes on the prefetch worker, one bounded part at a time."""
    for episode, path, fps, key in episodes:
        started = time.monotonic()
        with path.open("rb") as stream:
            source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        print(
            "FLORA_RUNTIME "
            + json.dumps(
                {
                    "event": "episode_hash",
                    "episode": episode["episode_index"],
                    "elapsed_s": round(time.monotonic() - started, 3),
                }
            ),
            flush=True,
        )
        for part, videos in reader(
            root, episode["episode_index"], path, episode["length"], image_key=key
        ):
            yield part, videos, episode, path, fps, key, source_hash


def run_direct(args, root, output, episodes):
    captioner = str(Path(__file__).resolve().parents[2] / "captioner")
    if captioner not in sys.path:
        sys.path.insert(0, captioner)
    from batch_utils.config import MODELS
    from batch_utils.dataset import inspect_episode, iter_episode_parts
    from batch_utils.models import Session
    from batch_utils.pipeline import segment
    from batch_utils.segment_output import boundary_flags, frame_span

    resume = getattr(args, "resume", False)
    if args.instruction and len(args.instruction.strip()) > 2000:
        raise ValueError("instruction must be at most 2000 characters")
    code_digest = hashlib.sha256()
    paths = sorted((Path(captioner) / "batch_utils").glob("*.py"))
    paths += [
        Path(captioner) / "batch_utils" / "models.json",
        Path(__file__),
        Path(__file__).with_name("prefetch.py"),
    ]
    for code_path in paths:
        code_digest.update(code_path.name.encode())
        code_digest.update(code_path.read_bytes())
    session = None
    resources = ExitStack()
    entries = []
    count = 0
    try:
        parts = resources.enter_context(
            closing(
                prefetch_parts(
                    iter_dataset_parts(root, episodes, iter_episode_parts),
                    limit=args.max_parts,
                )
            )
        )
        for part, videos, episode, path, fps, key, source_hash in parts:
            video = videos["main"]
            name = f"episode_{episode['episode_index']:06d}_part_{part['part']:04d}"
            job = {
                "id": name,
                "video": str(path),
                "source": str(path),
                "episode_index": episode["episode_index"],
                "fps": fps,
                "camera": key,
                "input_type": "parquet",
                **{k: part[k] for k in ("start_frame", "frames", "offset_s")},
            }
            inspection = inspect_episode(videos, "YAM")
            print(json.dumps(inspection, allow_nan=False), flush=True)
            identity = {
                "code_sha256": code_digest.hexdigest(),
                "source_sha256": source_hash,
                "chunk_sha256": video.sha256,
                "part": job,
                "model_revisions": {k: MODELS[k] for k in ("tempseg", "tempseg_base")},
                "instruction": args.instruction,
                "include_flags": args.include_flags,
                "flag_merge_gap": args.flag_merge_gap,
                "weights_path": str(args.weights_path.resolve())
                if args.weights_path
                else None,
            }
            if args.weights_path and resume:
                raise ValueError("Resume with a custom checkpoint is not supported")
            result_path = output / (name + ".json")
            if args.run:
                if result_path.exists():
                    existing = json.loads(result_path.read_text(encoding="utf-8"))
                    if not resume or existing.get("resume_identity") != identity:
                        raise FileExistsError(
                            f"Existing result does not match resume identity: {result_path}"
                        )
                else:
                    import torch

                    if not torch.cuda.is_available():
                        raise RuntimeError("CUDA is required for inference")
                    if session is None:
                        session = Session(tempseg_weights_path=args.weights_path)
                    torch.cuda.reset_peak_memory_stats()
                    started = time.monotonic()
                    segments, audit = segment(
                        videos,
                        "yam",
                        session,
                        args.instruction,
                        lambda fraction, desc="": print(
                            f"{fraction:.0%} {desc}", file=sys.stderr, flush=True
                        ),
                    )
                    print(
                        "FLORA_RUNTIME "
                        + json.dumps(
                            {
                                "event": "part_resources",
                                "part": name,
                                "elapsed_s": round(time.monotonic() - started, 3),
                                "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                                "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                                "process_peak_rss_kib": resource.getrusage(
                                    resource.RUSAGE_SELF
                                ).ru_maxrss,
                            }
                        ),
                        flush=True,
                    )
                    rows = []
                    for item in segments:
                        if (
                            not 0
                            <= item["start_s"]
                            < item["end_s"]
                            <= video.duration_s + 0.001
                        ):
                            raise RuntimeError(
                                "The pipeline returned an invalid segment interval"
                            )
                        first, last = frame_span(video, item["start_s"], item["end_s"])
                        rows.append(
                            {
                                "start_s": item["start_s"] + part["offset_s"],
                                "end_s": item["end_s"] + part["offset_s"],
                                "start_frame": first + part["start_frame"],
                                "end_frame": last + part["start_frame"],
                                "metadata": item["metadata"],
                                "segmentation_provenance": item["metadata"].get(
                                    "segmentation_provenance", "fine"
                                ),
                            }
                        )
                    result = {
                        "schema_version": "flora_tempseg_v1",
                        "duration_s": video.duration_s,
                        "segments": rows,
                        "profile": "YAM",
                        "camera_roles": ["main"],
                        "model_revisions": identity["model_revisions"],
                        "input_sha256": {"main": video.sha256},
                        "input_type": "parquet",
                        "frame_clock": "zero-based native frame position; end_frame is exclusive",
                        "episode_source": {
                            k: v for k, v in job.items() if k != "video"
                        },
                        "resume_identity": identity,
                    }
                    if args.include_flags:
                        local = [
                            {
                                "start_frame": r["start_frame"] - part["start_frame"],
                                "end_frame": r["end_frame"] - part["start_frame"],
                            }
                            for r in rows
                        ]
                        result["flags"] = [
                            v + part["start_frame"]
                            for v in boundary_flags(
                                local, part["frames"], args.flag_merge_gap
                            )
                        ]
                    atomic_json(result_path, result)
                    print(
                        json.dumps({"output": str(result_path), "segments": len(rows)}),
                        flush=True,
                    )
            entries.append(job)
            count += 1
            del videos, video
        manifest = {
            "dataset": str(root),
            "kind": "dagger",
            "validated": True,
            "inference": args.run,
            "mode": "tempseg" if args.run else "validate",
            "parts": entries,
        }
        atomic_json(output / "manifest.json", manifest)
        print(
            json.dumps(
                {
                    "manifest": str(output / "manifest.json"),
                    "validated_parts": count,
                    "inference": args.run,
                }
            ),
            flush=True,
        )
    finally:
        try:
            resources.close()
        finally:
            if session is not None:
                session.close()
