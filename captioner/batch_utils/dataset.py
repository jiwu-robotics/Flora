"""Read embedded JPEG episodes without creating intermediate video files."""

import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path

from PIL import Image

from .config import MAX_DURATION_S, MAX_FRAME_COUNT, MAX_UPLOAD_BYTES
from .media import InputError, Video

CAMERA = "observation.images.high_cam"


def episode_paths(dataset_path, selected=None):
    root = Path(dataset_path).expanduser().resolve(strict=True)
    if selected is not None and selected < 0:
        raise InputError("episode-index must be nonnegative")
    info = json.loads((root / "meta/info.json").read_text())
    metadata = root / "meta/episodes.jsonl"
    items = []
    if metadata.exists() and "data_path" in info:
        chunks = info["chunks_size"]
        if not isinstance(chunks, int) or isinstance(chunks, bool) or chunks < 1:
            raise InputError("Invalid dataset chunks_size")
        for line in metadata.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            index = row["episode_index"]
            if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                raise InputError("Invalid episode_index")
            if selected is None or index == selected:
                path = (
                    root
                    / info["data_path"].format(
                        episode_chunk=index // chunks, episode_index=index
                    )
                ).resolve(strict=True)
                items.append((index, path, row.get("length")))
    else:
        for path in root.glob("data/chunk-*/episode_*.parquet"):
            suffix = path.stem.removeprefix("episode_")
            if suffix.isascii() and suffix.isdigit():
                index = int(suffix)
                if selected is None or index == selected:
                    items.append((index, path.resolve(strict=True), None))
    seen = set()
    for index, path, _ in items:
        if not path.is_relative_to(root) or not path.is_file():
            raise InputError(f"Invalid dataset episode path: {path}")
        if index in seen:
            raise InputError(f"Duplicate episode index: {index}")
        seen.add(index)
    if not items:
        raise InputError("No matching episode Parquet files found")
    return sorted(items)


def load_episode(
    dataset_path, episode_index, path, expected_frames=None, *, image_key=CAMERA
):
    if not isinstance(image_key, str) or not image_key.strip():
        raise InputError("image-key must be a nonempty column name")
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise InputError(
            "Parquet input requires pyarrow; install requirements/jiwu.txt"
        ) from error
    info = json.loads(
        (Path(dataset_path).expanduser().resolve() / "meta/info.json").read_text()
    )
    fps = Fraction(str(info["fps"]))
    if fps < 4:
        raise InputError("Dataset frame rate must be at least 4 FPS")
    parquet = pq.ParquetFile(path)
    # This interface accepts per-episode files, not a multi-episode archive.
    count = parquet.metadata.num_rows
    if not 2 <= count <= MAX_FRAME_COUNT:
        raise InputError(f"Episode must contain 2 to {MAX_FRAME_COUNT} frames")
    if expected_frames is not None and count != expected_frames:
        raise InputError("Parquet frame count differs from episode metadata")
    columns = [image_key, "relative_timestamp_sec", "frame_index", "episode_index"]
    if not set(columns) <= set(parquet.schema_arrow.names):
        raise InputError(f"Parquet requires columns: {columns}")
    # Validate the clock before materializing image payloads.
    clock = (
        parquet.read(columns=columns[1:])
        .sort_by([("frame_index", "ascending")])
        .to_pylist()
    )
    pts = []
    for i, row in enumerate(clock):
        if row["episode_index"] != episode_index or row["frame_index"] != i:
            raise InputError(
                "Episode frames must have one episode ID and contiguous frame_index starting at zero"
            )
        if row["relative_timestamp_sec"] is None:
            raise InputError("Missing frame timestamp")
        pts.append(Fraction(str(row["relative_timestamp_sec"])) * 1_000_000)
    if any(b <= a for a, b in zip(pts, pts[1:])):
        raise InputError("Dataset frame timestamps must be strictly increasing")
    pts = [t - pts[0] for t in pts]
    duration = round(pts[-1] + 1_000_000 / fps)
    if duration > MAX_DURATION_S * 1_000_000:
        raise InputError(
            f"Episode exceeds {MAX_DURATION_S:g} seconds; split it before inference"
        )
    images = [None] * count
    size = None
    total = 0
    for batch in parquet.iter_batches(
        batch_size=32, columns=[image_key, "frame_index"]
    ):
        for row in batch.to_pylist():
            value = row[image_key]
            payload = value.get("bytes") if isinstance(value, dict) else None
            if not payload or not payload.startswith(b"\xff\xd8"):
                raise InputError(f"Missing or non-JPEG frame in {image_key}")
            total += len(payload)
            if total > MAX_UPLOAD_BYTES:
                raise InputError(
                    "Episode JPEG payload exceeds 256 MiB; split it before inference"
                )
            try:
                with Image.open(io.BytesIO(payload)) as image:
                    if min(image.size) <= 0 or max(image.size) > 4096:
                        raise InputError(
                            "Dataset image dimensions must be at most 4096 pixels per side"
                        )
                    if size is not None and size != image.size:
                        raise InputError("Dataset image dimensions must be consistent")
                    size = image.size
                    image.load()
            except OSError as error:
                raise InputError(
                    f"A JPEG in {image_key} could not be decoded"
                ) from error
            images[row["frame_index"]] = payload
    with Path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    cfr = all(abs(t - i * 1_000_000 / fps) <= 1 for i, t in enumerate(pts))
    return {
        "main": Video(
            Path(path), digest, fps, tuple(pts), duration, size, cfr, tuple(images)
        )
    }


def inspect_episode(videos, profile):
    main = videos["main"]
    return dict(
        status="inputs_validated",
        profile=profile,
        yam32=False,
        input_type="parquet",
        new_model_calls=0,
        duration_s=main.duration_s,
        cameras={
            "main": dict(
                sha256=main.sha256,
                source_fps=str(main.rate),
                frames=len(main.pts_us),
                size=list(main.size),
                constant_frame_rate=main.cfr,
                duration_s=main.duration_s,
            )
        },
    )
