"""Native TempSeg result contract; no platform execution or publication state."""

import hashlib
import json
import math
import os
from bisect import bisect_left
from fractions import Fraction
from pathlib import Path

from .direct import atomic_json

SCHEMA_VERSION = "flora_results_v1"
MAX_RESULT_BYTES = 8 * 1024 * 1024
REPO = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative_file(root, path):
    path = Path(path)
    if not path.is_absolute():
        if ".." in path.parts:
            raise ValueError("Source path contains parent traversal")
        path = root / path
    if ".." in path.parts or not path.is_relative_to(root):
        raise ValueError("Source path escapes dataset root")
    if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
        raise ValueError("Source is not a regular file inside dataset root")
    return path.relative_to(root).as_posix()


def snapshot(root, paths):
    return [
        {"path": name, "sha256": digest(root / name)}
        for name in sorted({relative_file(root, p) for p in paths})
    ]


def code_identity():
    paths = sorted((REPO / "src/infer").glob("*.py"))
    paths += sorted((REPO / "captioner").rglob("*.py"))
    paths += [
        REPO / "captioner/batch_utils/models.json",
        REPO / "captioner/batch_utils/CODE_MANIFEST.json",
    ]
    value = hashlib.sha256()
    for path in paths:
        value.update(path.relative_to(REPO).as_posix().encode() + b"\0")
        value.update(bytes.fromhex(digest(path)))
    return "sha256:" + value.hexdigest()


def model_identity(weights):
    models = json.loads((REPO / "captioner/batch_utils/models.json").read_text())
    for model in models.values():
        if model.get("repo_env", "") in os.environ:
            model["repo"] = os.environ[model["repo_env"]]
            if not model["repo"]:
                raise ValueError("Configured model repository is empty")
    if weights is None:
        return {key: models[key] for key in ("tempseg", "tempseg_base")}, None
    root = weights.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Custom merged weights must be a directory")
    files = snapshot(root, [p for p in root.rglob("*") if p.is_file()])
    if not files:
        raise ValueError("Custom merged weights directory is empty")
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {
        "tempseg": {
            "kind": "custom_merged",
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "digest_policy": "sorted_relative_files_sha256_v1",
            "files": files,
        }
    }, root


def merged_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start < merged[-1][1]:
            raise ValueError("Overlapping or duplicate part coverage")
        if merged and start == merged[-1][1]:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def verify_row_clock(
    path, episode_index, frame_count, video, start_frame=0, offset_s=0, *, direct_parquet=False
):
    """Prove row order and normalized source timestamps match presentation PTS.

    Direct Parquet decoding uses relative_timestamp_sec even when timestamp
    records a wall clock with capture gaps. External video keeps its original
    timestamp contract; neither path substitutes nominal frame-rate timing.
    """
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    columns = parquet.schema_arrow.names
    clock = (
        "relative_timestamp_sec" if direct_parquet
        else "timestamp" if "timestamp" in columns else "relative_timestamp_sec"
    )
    if not {clock, "frame_index", "episode_index"} <= set(columns):
        raise ValueError("Cannot prove source row to presentation timestamp mapping")
    if parquet.metadata.num_rows != frame_count:
        raise ValueError("Source row count differs from episode metadata")
    first = previous = None
    count = 0
    for batch in parquet.iter_batches(columns=[clock, "frame_index", "episode_index"]):
        for row in batch.to_pylist():
            stamp = row[clock]
            if (
                row["frame_index"] != count
                or row["episode_index"] != episode_index
                or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp)
            ):
                raise ValueError("Invalid source row identity or timestamp")
            if previous is not None and stamp <= previous:
                raise ValueError("Source timestamps must be strictly increasing")
            if first is None:
                first = stamp
            local = count - start_frame
            if 0 <= local < len(video.pts_us):
                expected = float(video.pts_us[local]) + offset_s * 1_000_000
                if abs((stamp - first) * 1_000_000 - expected) > 1.01:
                    raise ValueError(
                        "Source row timestamp does not match video presentation PTS"
                    )
            previous = stamp
            count += 1


def local_time(value, offset, video):
    """Undo float offset addition without shifting exact native frame boundaries."""
    if not math.isfinite(value):
        raise ValueError("Non-finite segment time")
    local = Fraction(str(value)) - Fraction(str(offset))
    pts = video.pts_us
    position = bisect_left(pts, local * 1_000_000)
    tolerance = max(math.ulp(value), math.ulp(offset)) * 4
    candidates = list(pts[max(0, position - 1) : position + 1])
    candidates.extend([0, Fraction(str(video.duration_s)) * 1_000_000])
    for candidate in candidates:
        seconds = Fraction(candidate) / 1_000_000
        if abs(local - seconds) <= tolerance:
            return seconds
    return local


class Results:
    """Own the selected input inventory and accept each proven part exactly once."""

    def __init__(self, args, root, output, episodes, metadata):
        self.args, self.root, self.output = args, root, output
        self.key = getattr(args, "dataset_key", None) or root.name
        self.models, self.weights = model_identity(getattr(args, "weights_path", None))
        self.producer = {
            "name": "flora",
            "revision": code_identity(),
            "models": self.models,
        }
        self.parameters = {
            "episode_index": args.episode,
            "max_parts": args.max_parts,
            "inference": args.run,
            "direct_parquet": getattr(args, "direct_parquet", False),
            "image_key": episodes[0][3],
            "include_flags": getattr(args, "include_flags", False),
            "flag_merge_gap": getattr(args, "flag_merge_gap", 30),
            "instruction": getattr(args, "instruction", ""),
            "profile": "yam" if args.kind == "dagger" else "human",
        }
        self.entries, self.parts, self.ranges, self.checked = {}, set(), {}, {}
        info = json.loads((root / "meta/info.json").read_text())
        for episode, path, fps, key in episodes:
            index, count = episode["episode_index"], episode["length"]
            if type(count) is not int or count < 2:
                raise ValueError("Invalid episode length")
            if args.kind == "dagger":
                parquet = path
            else:
                template = Path(
                    info["data_path"].format(
                        episode_chunk=index // info["chunks_size"], episode_index=index
                    )
                )
                if template.is_absolute():
                    raise ValueError("Dataset path template must be relative")
                parquet = root / template
            name = relative_file(root, parquet)
            files = snapshot(
                root, [root / m["path"] for m in metadata] + [path, parquet]
            )
            if any(m not in files for m in metadata):
                raise ValueError("Dataset metadata changed during selection")
            self.entries[index] = {
                "parquet_name": name,
                "frame_count": count,
                "source": {
                    "kind": args.kind,
                    "input_type": "parquet" if args.kind == "dagger" else "video",
                    "camera_key": key,
                    "files": files,
                },
                "status": "not_processed",
                "processed_ranges": [],
                "segments": [],
            }
            self.ranges[index], self.checked[index] = [], []
        self.selection = {
            "dataset_key": self.key,
            "episodes": [
                {"chunk": Path(row["parquet_name"]).parent.name, "episode_index": index}
                for index, row in self.entries.items()
            ],
        }
        self.identity = {
            "producer": self.producer,
            "parameters": self.parameters,
            "selection": self.selection,
            "sources": {str(i): row["source"] for i, row in self.entries.items()},
        }
        identity_path = output / "results.identity.json"
        self.identity_sha256 = hashlib.sha256(
            json.dumps(self.identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if getattr(args, "resume", False):
            # A failed resumed attempt must never expose an old success file.
            (output / "results.json").unlink(missing_ok=True)
            if json.loads(identity_path.read_text()) != self.identity:
                raise ValueError("Native results resume identity mismatch")
        elif identity_path.exists() or (output / "results.json").exists():
            raise FileExistsError(
                "Native results already exist; use a new output directory"
            )
        atomic_json(identity_path, self.identity)

    def validate_video(self, job, video):
        row = self.entries[job["episode_index"]]
        if row["source"]["input_type"] == "video":
            name = relative_file(self.root, job["source"])
            if {"path": name, "sha256": video.sha256} not in row["source"]["files"]:
                raise ValueError("Decoded video digest differs from source inventory")
        verify_row_clock(
            self.root / row["parquet_name"],
            job["episode_index"],
            row["frame_count"],
            video,
            job["start_frame"],
            job["offset_s"],
            direct_parquet=row["source"]["input_type"] == "parquet",
        )

    def add(self, job, video, result=None):
        from batch_utils.segment_output import frame_span

        index, name = job["episode_index"], job["id"]
        row = self.entries[index]
        start, end = job["start_frame"], job["start_frame"] + job["frames"]
        if name in self.parts or not 0 <= start < end <= row["frame_count"]:
            raise ValueError("Duplicate part or invalid part coverage")
        if len(video.pts_us) != end - start:
            raise ValueError("Part frame count mismatch")
        merged_ranges(self.checked[index] + [(start, end)])
        segments = []
        if result is not None:
            if result["input_sha256"]["main"] != video.sha256:
                raise ValueError("Part input digest mismatch")
            for segment in result["segments"]:
                first = local_time(segment["start_s"], job["offset_s"], video)
                last = local_time(segment["end_s"], job["offset_s"], video)
                if not (
                    math.isfinite(first)
                    and math.isfinite(last)
                    and 0 <= first < last <= Fraction(str(video.duration_s))
                ):
                    raise ValueError("Invalid or out-of-bounds segment time")
                a, b = frame_span(video, first, last)
                if (segment["start_frame"], segment["end_frame"]) != (
                    a + start,
                    b + start,
                ):
                    raise ValueError("Segment frame mapping mismatch")
                segments.append(
                    {
                        k: segment[k]
                        for k in (
                            "start_frame",
                            "end_frame",
                            "start_s",
                            "end_s",
                            "segmentation_provenance",
                        )
                    }
                    | {"part_id": name}
                )
        self.parts.add(name)
        self.checked[index].append((start, end))
        if result is not None:
            self.ranges[index].append((start, end))
            row["segments"].extend(segments)

    def write(self, failed=False):
        from batch_utils.segment_output import boundary_flags

        changed = False
        try:
            for row in self.entries.values():
                files = row["source"]["files"]
                if snapshot(self.root, [f["path"] for f in files]) != files:
                    changed = True
            if model_identity(self.weights)[0] != self.models:
                changed = True
            if code_identity() != self.producer["revision"]:
                changed = True
        except (OSError, ValueError):
            changed = True
        for index, row in self.entries.items():
            ranges = merged_ranges(self.ranges[index])
            row["processed_ranges"] = [
                {"start_frame": a, "end_frame": b} for a, b in ranges
            ]
            if failed or changed:
                row["status"] = "failed"
                row["error"] = {
                    "code": "source_changed" if changed else "execution_failed",
                    "message": "Input/code/model identity changed"
                    if changed
                    else "Execution did not finish; inspect local logs",
                }
            elif self.args.run:
                row["status"] = (
                    "success"
                    if ranges == [[0, row["frame_count"]]]
                    else "partial"
                    if ranges
                    else "not_processed"
                )
            else:
                row["status"] = (
                    "validated"
                    if merged_ranges(self.checked[index]) == [[0, row["frame_count"]]]
                    else "not_processed"
                )
            row["segments"].sort(
                key=lambda s: (
                    s["start_frame"],
                    s["end_frame"],
                    s["start_s"],
                    s["end_s"],
                    s["part_id"],
                )
            )
            if self.parameters["include_flags"]:
                row["flags"] = boundary_flags(
                    row["segments"],
                    row["frame_count"],
                    self.parameters["flag_merge_gap"],
                )
        results = {}
        for index, row in self.entries.items():
            results.setdefault(Path(row["parquet_name"]).parent.name, {})[
                str(index)
            ] = row
        document = {
            "schema_version": SCHEMA_VERSION,
            "producer": self.producer,
            "mode": "tempseg",
            "parameters": self.parameters,
            "selection": self.selection,
            "coordinates": {
                "frames": "original_episode_row_index",
                "interval": "half_open",
                "seconds": "relative_to_first_source_presentation_timestamp",
                "frame_mapping": "flora_frame_span_v1",
            },
            "flags_policy": "episode_boundaries_v1",
            "complete": all(
                row["status"] == "success" for row in self.entries.values()
            ),
            "results": {self.key: results},
        }
        if (
            len(
                (
                    json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n"
                ).encode()
            )
            > MAX_RESULT_BYTES
        ):
            raise ValueError("Native results exceed 8 MiB; select fewer episodes")
        atomic_json(self.output / "results.json", document)
        print(
            json.dumps(
                {
                    "results": str(self.output / "results.json"),
                    "complete": document["complete"],
                }
            ),
            flush=True,
        )
        if changed:
            raise ValueError("Source, code or model changed during execution")
