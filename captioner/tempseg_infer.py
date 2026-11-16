"""Run only the temporal segmentation stage of the annotation pipeline."""

import json
import math
import sys
import time
from pathlib import Path

from batch_utils.api import DataEnginePipeline
from batch_utils.cli import jobs, parser
from batch_utils.config import MODELS, PROFILE_POOLS


def main(argv=None):
    p = parser(dataset_input=True)
    p.add_argument(
        "--image-key",
        help="Parquet JPEG column (default: observation.images.high_cam); requires --dataset-path.",
    )
    p.add_argument(
        "--weights-path",
        "--weights",
        type=Path,
        help="Local merged TempSeg checkpoint; default uses pinned base + adapter.",
    )
    p.add_argument(
        "--include-flags",
        action="store_true",
        help="Include merged boundary flags in native frame coordinates.",
    )
    p.add_argument(
        "--flag-merge-gap",
        type=int,
        default=30,
        help="Merge adjacent flags less than this many frames apart; 0 disables merging.",
    )
    p.description = "FLORA TempSeg: timestamped action intervals without captions."
    p.set_defaults(profile=None)
    args = p.parse_args(argv)
    args.profile = args.profile or ("yam" if args.dataset_path else "human")
    if args.flag_merge_gap < 0 or (
        args.episode_index is not None and args.episode_index < 0
    ):
        p.error("episode-index and flag-merge-gap must be nonnegative")
    if args.episode_index is not None and not args.dataset_path:
        p.error("--episode-index requires --dataset-path")
    if args.dataset_path and (args.left_wrist or args.right_wrist or args.yam32):
        p.error(
            "Parquet input supports one image camera; wrist cameras and yam32 are unavailable"
        )
    if args.image_key is not None and (
        not args.dataset_path or not args.image_key.strip()
    ):
        p.error("--image-key requires --dataset-path and a nonempty column name")
    args.image_key = args.image_key or "observation.images.high_cam"
    session = None
    try:
        if args.dataset_path:
            from batch_utils.dataset import episode_paths

            episodes = episode_paths(args.dataset_path, args.episode_index)
            if args.output and (len(episodes) != 1 or args.output_dir):
                p.error(
                    "--output requires exactly one episode and cannot be combined with --output-dir"
                )
            if not args.validate_only and not (args.output or args.output_dir):
                p.error("Parquet inference requires --output or --output-dir")
            profile = args.profile
            items = [
                (
                    dict(episode=ep, profile=profile, instruction=args.instruction),
                    args.output
                    or (args.output_dir or Path(".")) / f"episode_{ep[0]:06d}.json",
                )
                for ep in episodes
            ]
        else:
            items = jobs(args, p)
        if not args.validate_only and not args.overwrite:
            for _, output in items:
                if output.exists():
                    raise FileExistsError(
                        f"Output already exists: {output}. Use --overwrite to replace it."
                    )
        for kwargs, output in items:
            if args.dataset_path:
                from batch_utils.dataset import load_episode, inspect_episode

                videos = load_episode(
                    args.dataset_path, *kwargs["episode"], image_key=args.image_key
                )
                profile = {
                    "human": "Human",
                    "yam": "YAM",
                    "dex": "Dex",
                    "tianji": "Tianji",
                }[kwargs["profile"]]
                if len(kwargs["instruction"].strip()) > 2000:
                    raise ValueError("instruction must be at most 2000 characters")
                inspection = inspect_episode(videos, profile)
                inspection["image_key"] = args.image_key
            else:
                videos, profile = DataEnginePipeline._inputs(
                    kwargs["video"],
                    kwargs.get("profile", "human"),
                    kwargs.get("left_wrist"),
                    kwargs.get("right_wrist"),
                    kwargs.get("yam32", False),
                    kwargs.get("instruction", ""),
                )
                from batch_utils.dataset import inspect_episode

                inspection = inspect_episode(videos, profile)
                inspection.update(input_type="video", yam32=kwargs.get("yam32", False))
                inspection["cameras"] = {
                    role: dict(
                        sha256=v.sha256,
                        source_fps=str(v.rate),
                        frames=len(v.pts_us),
                        size=list(v.size),
                        constant_frame_rate=v.cfr,
                        duration_s=v.duration_s,
                    )
                    for role, v in videos.items()
                }
            if args.validate_only:
                inspection["model_revisions"] = {
                    key: MODELS[key] for key in ("tempseg", "tempseg_base")
                }
                print(json.dumps(inspection, allow_nan=False))
                continue
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError(
                    "CUDA is required for inference. Use --validate-only to check inputs on CPU."
                )
            from batch_utils.models import Session, runtime_event
            from batch_utils.pipeline import segment

            pool = "yam32" if kwargs.get("yam32", False) else PROFILE_POOLS[profile]
            if session is None:
                session = Session(tempseg_weights_path=args.weights_path)
            started = time.monotonic()
            segments, audit = segment(
                videos,
                pool,
                session,
                kwargs.get("instruction", ""),
                lambda fraction, desc="": print(
                    f"{fraction:.0%} {desc}", file=sys.stderr, flush=True
                ),
            )
            rows = []
            for item in segments:
                start, end = item["start_s"], item["end_s"]
                if not (
                    math.isfinite(start)
                    and math.isfinite(end)
                    and 0 <= start < end <= videos["main"].duration_s + 0.001
                ):
                    raise RuntimeError(
                        "The pipeline returned an invalid segment interval."
                    )
                from batch_utils.segment_output import frame_span

                first, last = frame_span(videos["main"], start, end)
                rows.append(
                    dict(
                        start_s=start,
                        end_s=end,
                        start_frame=first,
                        end_frame=last,
                        metadata=item["metadata"],
                        segmentation_provenance=item["metadata"].get(
                            "segmentation_provenance", "fine"
                        ),
                    )
                )
            runtime_event(
                "segmentation_complete", windows=len(audit), segments=len(rows)
            )
            result = dict(
                schema_version="flora_tempseg_v1",
                duration_s=videos["main"].duration_s,
                segments=rows,
                elapsed_s=round(time.monotonic() - started, 2),
                source_clock="seconds relative to the first native source presentation timestamp",
                profile=profile,
                camera_roles=list(videos),
                model_revisions={
                    key: MODELS[key] for key in ("tempseg", "tempseg_base")
                },
                input_sha256={role: video.sha256 for role, video in videos.items()},
            )
            result["input_type"] = "parquet" if args.dataset_path else "video"
            result["frame_clock"] = (
                "zero-based native frame position; end_frame is exclusive"
            )
            if args.dataset_path:
                result["dataset_source"] = dict(
                    episode_index=kwargs["episode"][0],
                    camera=args.image_key,
                    path=str(kwargs["episode"][1]),
                )
            if args.include_flags:
                from batch_utils.segment_output import boundary_flags

                result["flags"] = boundary_flags(
                    rows, len(videos["main"].pts_us), args.flag_merge_gap
                )
            if args.include_audit:
                result["temporal_windows"] = audit
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w" if args.overwrite else "x") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write("\n")
            print(json.dumps({"output": str(output), "segments": len(rows)}))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"FLORA inference failed: {error}", file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
