"""Caption previously segmented action intervals using the standard Flora pipeline."""

import argparse
import json
import math
import sys
import time
from pathlib import Path

from batch_utils.api import DataEnginePipeline
from batch_utils.config import MODELS


def checked_segments(payload, inspection):
    if payload.get("schema_version") != "flora_tempseg_v1":
        raise ValueError("Expected a Flora TempSeg result.")
    if payload.get("input_sha256") != {
        role: data["sha256"] for role, data in inspection["cameras"].items()
    }:
        raise ValueError("Segment input video hashes do not match the current videos.")
    if payload.get("profile") != inspection["profile"]:
        raise ValueError("Segment profile does not match the current profile.")
    rows = payload.get("segments")
    if not isinstance(rows, list):
        raise ValueError("segments must be a list.")
    segments = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each segment must be an object.")
        start, end = row.get("start_s"), row.get("end_s")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not math.isfinite(start)
            or not math.isfinite(end)
            or not 0 <= start < end <= inspection["duration_s"] + 0.001
        ):
            raise ValueError("Invalid segment interval.")
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("Segment metadata must be an object.")
        segments.append(
            dict(
                start_s=start,
                end_s=end,
                metadata={
                    **metadata,
                    "segmentation_provenance": row.get(
                        "segmentation_provenance", "fine"
                    ),
                },
            )
        )
    return segments


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument(
        "--profile", choices=["human", "yam", "dex", "tianji"], required=True
    )
    p.add_argument("--segments", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.output.exists():
            raise FileExistsError(args.output)
        engine = DataEnginePipeline()
        inspection = engine.inspect_inputs(args.video, profile=args.profile)
        payload = json.loads(args.segments.read_text(encoding="utf-8"))
        segments = checked_segments(payload, inspection)
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for inference.")
        from batch_utils.models import Session, runtime_event
        from batch_utils.pipeline import caption_single

        videos, profile = engine._inputs(
            args.video, args.profile, None, None, False, ""
        )
        session = Session()
        started = time.monotonic()
        try:
            captions, _ = caption_single(
                videos,
                segments,
                profile,
                session,
                "",
                lambda fraction, desc="": print(
                    f"{fraction:.0%} {desc}", file=sys.stderr, flush=True
                ),
            )
        finally:
            session.close()
        for row, source in zip(captions, segments, strict=True):
            row["segmentation_provenance"] = source["metadata"][
                "segmentation_provenance"
            ]
        result = dict(
            schema_version="flora_demo_annotation_v1",
            duration_s=videos["main"].duration_s,
            segments=captions,
            elapsed_s=round(time.monotonic() - started, 2),
            source_clock="seconds relative to the first native source presentation timestamp",
            camera_roles=list(videos),
            profile=profile,
            model_revisions={
                "captioner": MODELS["captioner"],
                "segmentation_source": payload["model_revisions"],
            },
            input_sha256={role: video.sha256 for role, video in videos.items()},
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        runtime_event(
            "annotation_complete",
            segments=len(captions),
            complete_captions=sum(row["status"] == "complete" for row in captions),
        )
        print(json.dumps({"output": str(args.output), "segments": len(captions)}))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f"FLORA inference failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
