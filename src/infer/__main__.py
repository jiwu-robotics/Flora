"""Prepare Jiwu camera data and run Flora with episode-relative timestamps."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 240 * 1024 * 1024


def rows(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def source_path(root, template, episode, chunks_size, **extra):
    path = (root / template.format(episode_chunk=episode // chunks_size,
                                  episode_index=episode, **extra)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError(f"dataset path escapes root: {path}")
    return path


def dataset(root, kind, selected):
    info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
    fps, chunk = info["fps"], info["chunks_size"]
    if not isinstance(fps, (int, float)) or fps < 4 or not isinstance(chunk, int) or chunk < 1:
        raise ValueError("Invalid fps or chunk size in dataset metadata")
    episodes = list(rows(root / "meta/episodes.jsonl"))
    ids = [x["episode_index"] for x in episodes]
    if len(set(ids)) != len(ids) or any(not isinstance(x, int) or x < 0 for x in ids):
        raise ValueError("Invalid or duplicate episode index")
    if selected is not None:
        episodes = [x for x in episodes if x["episode_index"] == selected]
    if not episodes:
        raise ValueError("No matching episodes")
    key = "observation.images.high_cam" if kind == "dagger" else "observation.images.ego_l"
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
        return {"id": f"episode_{episode['episode_index']:06d}_part_{part:04d}",
                "video": str(target), "start_frame": start, "frames": count,
                "offset_s": start / fps}

    try:
        for batch in parquet.iter_batches(batch_size=64, columns=[key, "frame_index"]):
            images = batch.column(0).to_pylist()
            indices = batch.column(1).to_pylist()
            for image, index in zip(images, indices, strict=True):
                if index != start + count:
                    raise ValueError(f"Unexpected frame_index {index}; expected {start + count}")
                payload = image.get("bytes") if isinstance(image, dict) else None
                if not payload or not payload.startswith(b"\xff\xd8"):
                    raise ValueError(f"Missing or non-JPEG frame {index}")
                if process and (count >= max_frames or (size + len(payload) > MAX_BYTES and count >= 2)):
                    yield finish()
                    process = None
                    part += 1
                    start += count
                    count = size = 0
                    if max_parts and part >= max_parts:
                        return
                if process is None:
                    target = out / f"episode_{episode['episode_index']:06d}_part_{part:04d}.avi"
                    if target.exists():
                        raise FileExistsError(target)
                    process = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-vcodec", "mjpeg", "-i", "pipe:0", "-c:v", "copy", "-f", "avi", str(target)], stdin=subprocess.PIPE)
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


def run(args):
    root = args.dataset.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.json"
    if manifest.exists():
        raise FileExistsError(manifest)
    media = output / "media"
    media.mkdir(exist_ok=True)
    entries = []
    part_count = 0
    for episode, path, fps, key in dataset(root, args.kind, args.episode):
        remaining = args.max_parts - part_count if args.max_parts else 0
        if args.kind == "dagger":
            parts = dagger_parts(path, episode, fps, key, media, remaining)
        else:
            parts = [{"id": f"episode_{episode['episode_index']:06d}", "video": str(path),
                      "start_frame": 0, "frames": episode["length"], "offset_s": 0}]
        for part in parts:
            job = {**part, "episode_index": episode["episode_index"], "fps": fps,
                   "camera": key, "source": str(path)}
            command = [sys.executable, str(ROOT / "captioner/infer.py"), "--video", part["video"],
                       "--profile", "yam" if args.kind == "dagger" else "human"]
            checked = subprocess.run(command + ["--validate-only"], text=True, capture_output=True)
            print(checked.stdout, end="", flush=True)
            if checked.returncode:
                raise RuntimeError(checked.stderr.strip() or f"Input validation failed for {path}")
            inspection = json.loads(checked.stdout)
            camera = inspection["cameras"]["main"]
            if camera["frames"] != part["frames"]:
                raise ValueError(f"{path}: decoded frame count differs from episode metadata")
            if args.run:
                result_path = output / (part["id"] + ".json")
                subprocess.run(command + ["--output", str(result_path)], check=True)
                result = json.loads(result_path.read_text(encoding="utf-8"))
                for segment in result["segments"]:
                    segment["start_s"] += part["offset_s"]
                    segment["end_s"] += part["offset_s"]
                result["episode_source"] = {k: v for k, v in job.items() if k != "video"}
                result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                incomplete = [s for s in result["segments"] if s.get("status") != "complete"]
                if incomplete:
                    raise ValueError(f"{result_path}: {len(incomplete)} incomplete segments")
            entries.append(job)
            part_count += 1
            if args.max_parts and part_count >= args.max_parts:
                break
        if args.max_parts and part_count >= args.max_parts:
            break
    manifest.write_text(json.dumps({"dataset": str(root), "kind": args.kind, "validated": True,
                                    "inference": args.run, "parts": entries}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest), "validated_parts": len(entries), "inference": args.run}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--kind", choices=("dagger", "umi"), required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--episode", type=int)
    p.add_argument("--max-parts", type=int, default=0, help="Maximum parts to process, 0 means all")
    p.add_argument("--run", action="store_true", help="Run GPU inference after CPU validation")
    args = p.parse_args()
    if args.max_parts < 0 or (args.episode is not None and args.episode < 0):
        p.error("episode and max-parts must be non-negative")
    try:
        run(args)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Jiwu inference failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
