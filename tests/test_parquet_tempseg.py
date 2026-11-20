"""CPU checks for direct image input, frame boundaries, and batch model reuse."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "captioner"))
from batch_utils.segment_output import boundary_flags, frame_span

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from PIL import Image
    from batch_utils.dataset import episode_paths, load_episode
    from batch_utils.media import decode_selected
except ImportError:
    pa = None


class BoundaryTests(unittest.TestCase):
    def test_irregular_pts_and_exclusive_end(self):
        video = SimpleNamespace(pts_us=(0, 200000, 500000, 750000))
        self.assertEqual(frame_span(video, 0.3, 0.75), (1, 3))
        self.assertEqual(frame_span(video, 0, 1), (0, 4))

    def test_flags_use_strict_gap_and_transitive_groups(self):
        rows = [
            dict(start_frame=0, end_frame=100),
            dict(start_frame=120, end_frame=140),
            dict(start_frame=170, end_frame=291),
        ]
        self.assertEqual(boundary_flags(rows, 300, 30), [120, 170])
        self.assertEqual(boundary_flags(rows, 300, 0), [100, 120, 140, 170])


@unittest.skipIf(pa is None, "CPU image tests require pyarrow, Pillow, and av")
class ParquetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "meta").mkdir()
        (self.root / "meta/info.json").write_text(json.dumps({"fps": 4}))
        self.path = self.root / "data/chunk-000/episode_000000.parquet"
        self.path.parent.mkdir(parents=True)
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), "red").save(buf, format="JPEG")
        self.rows = [
            dict(
                episode_index=0,
                frame_index=i,
                relative_timestamp_sec=10 + i / 4,
                **{"observation.images.high_cam": {"bytes": buf.getvalue()}},
            )
            for i in range(12)
        ]
        self.write()

    def write(self):
        pq.write_table(pa.Table.from_pylist(list(reversed(self.rows))), self.path)

    def test_read_sort_normalize_and_decode_without_video(self):
        self.assertEqual(episode_paths(self.root)[0][0], 0)
        video = load_episode(self.root, 0, self.path)["main"]
        self.assertEqual(video.pts_us[0], 0)
        self.assertEqual(video.duration_s, 3)
        self.assertEqual(len(video.encoded_frames), 12)
        self.assertEqual(decode_selected(video, {1, 10})[1].size, (16, 16))
        self.assertFalse(list(self.root.rglob("*.avi")))

    def test_streaming_parts_preserve_frame_offsets(self):
        from batch_utils import dataset as reader

        pq.write_table(pa.Table.from_pylist(self.rows), self.path)
        with patch.object(reader, "MAX_FRAME_COUNT", 5):
            parts = list(reader.iter_episode_parts(self.root, 0, self.path, 12))
        self.assertEqual([p[0]["frames"] for p in parts], [5, 5, 2])
        self.assertEqual([p[0]["start_frame"] for p in parts], [0, 5, 10])
        self.assertEqual([p[0]["offset_s"] for p in parts], [0, 1.25, 2.5])
        self.assertEqual(parts[1][1]["main"].pts_us[0], 0)
        self.assertFalse(list(self.root.rglob("*.avi")))

    def test_custom_image_key_and_missing_column(self):
        import tempseg_infer

        key = "observation.images.front_cam"
        custom = [
            {
                **{k: v for k, v in row.items() if k != "observation.images.high_cam"},
                key: row["observation.images.high_cam"],
            }
            for row in self.rows
        ]
        pq.write_table(pa.Table.from_pylist(custom), self.path)
        video = load_episode(self.root, 0, self.path, image_key=key)["main"]
        self.assertEqual(len(video.encoded_frames), 12)
        with self.assertRaisesRegex(ValueError, "requires columns"):
            load_episode(self.root, 0, self.path)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = tempseg_infer.main(
                [
                    "--dataset-path",
                    str(self.root),
                    "--image-key",
                    key,
                    "--validate-only",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["image_key"], key)

    def test_invalid_clock_and_frame_ids(self):
        self.rows[1]["relative_timestamp_sec"] = 10
        self.write()
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            load_episode(self.root, 0, self.path)
        self.rows[1]["relative_timestamp_sec"] = 10.25
        self.rows[1]["frame_index"] = 9
        self.write()
        with self.assertRaisesRegex(ValueError, "contiguous"):
            load_episode(self.root, 0, self.path)

    def test_corrupt_jpeg_fails_preflight(self):
        self.rows[3]["observation.images.high_cam"]["bytes"] = b"\xff\xd8broken"
        self.write()
        with self.assertRaisesRegex(ValueError, "decoded"):
            load_episode(self.root, 0, self.path)

    def test_cli_validation_without_loading_weights(self):
        import tempseg_infer

        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = tempseg_infer.main(
                [
                    "--dataset-path",
                    str(self.root),
                    "--validate-only",
                    "--weights-path",
                    "/nonexistent/checkpoint",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["new_model_calls"], 0)
        self.assertEqual(payload["profile"], "YAM")
        self.assertEqual(payload["input_type"], "parquet")

    def test_output_compatibility_and_single_session_for_batch(self):
        import tempseg_infer
        from batch_utils import models, pipeline

        second = self.path.with_name("episode_000001.parquet")
        pq.write_table(
            pa.Table.from_pylist([{**r, "episode_index": 1} for r in self.rows]), second
        )
        session = SimpleNamespace(close=lambda: None)
        with (
            patch.object(models, "Session", return_value=session) as factory,
            patch.object(
                pipeline,
                "segment",
                return_value=([dict(start_s=0, end_s=1, metadata={})], []),
            ),
            patch("torch.cuda.is_available", return_value=True),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = tempseg_infer.main(
                [
                    "--dataset-path",
                    str(self.root),
                    "--output-dir",
                    str(self.root / "out"),
                    "--include-flags",
                ]
            )
        self.assertEqual(code, 0)
        factory.assert_called_once()
        result = json.loads((self.root / "out/episode_000000.json").read_text())
        self.assertEqual(result["schema_version"], "flora_tempseg_v1")
        self.assertEqual(result["segments"][0]["end_s"], 1)
        self.assertEqual(result["segments"][0]["end_frame"], 4)
        self.assertIn("input_sha256", result)
        self.assertIn("flags", result)

    def test_adapter_direct_resume_reuses_model_and_results(self):
        from src.infer import __main__ as adapter
        from batch_utils import models, pipeline, dataset as reader

        pq.write_table(pa.Table.from_pylist(self.rows), self.path)
        (self.root / "meta/episodes.jsonl").write_text(
            json.dumps({"episode_index": 0, "length": 12}) + "\n"
        )
        args = SimpleNamespace(
            dataset=self.root,
            output=self.root / "out",
            kind="dagger",
            episode=0,
            max_parts=0,
            run=True,
            mode="tempseg",
            segments_dir=None,
            direct_parquet=True,
            weights_path=None,
            include_flags=False,
            flag_merge_gap=30,
            instruction="",
            resume=False,
        )
        session = SimpleNamespace(close=lambda: None)
        episodes = [
            (
                {"episode_index": 0, "length": 12},
                self.path,
                4,
                "observation.images.high_cam",
            )
        ]
        with (
            patch.object(adapter, "dataset", return_value=episodes),
            patch.object(reader, "MAX_FRAME_COUNT", 5),
            patch.object(models, "Session", return_value=session) as factory,
            patch.object(
                pipeline,
                "segment",
                return_value=([dict(start_s=0, end_s=0.5, metadata={})], []),
            ) as predict,
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.reset_peak_memory_stats"),
            patch("torch.cuda.max_memory_allocated", return_value=0),
            patch("torch.cuda.max_memory_reserved", return_value=0),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            adapter.run(args)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(predict.call_count, 3)
            result = json.loads(
                (args.output / "episode_000000_part_0001.json").read_text()
            )
            self.assertEqual(result["segments"][0]["start_s"], 1.25)
            self.assertEqual(result["segments"][0]["start_frame"], 5)
            args.resume = True
            adapter.run(args)
            self.assertEqual(predict.call_count, 3)
            self.assertFalse(list(self.root.rglob("*.avi")))
            aggregate = json.loads((args.output / "results.json").read_text())
            self.assertTrue(aggregate["complete"])
            episode = aggregate["results"][self.root.name]["chunk-000"]["0"]
            self.assertEqual(len(episode["segments"]), 3)
            self.assertEqual(
                episode["processed_ranges"], [{"start_frame": 0, "end_frame": 12}]
            )
            self.assertEqual(
                [s["start_frame"] for s in episode["segments"]], [0, 5, 10]
            )

    def test_streaming_avoids_single_frame_tail(self):
        from batch_utils import dataset as reader

        pq.write_table(pa.Table.from_pylist(self.rows[:11]), self.path)
        with patch.object(reader, "MAX_FRAME_COUNT", 5):
            parts = list(reader.iter_episode_parts(self.root, 0, self.path, 11))
        self.assertEqual([p[0]["frames"] for p in parts], [5, 4, 2])

    def test_session_reuses_loaded_model(self):
        from batch_utils.models import Session

        session = Session()
        session.kind = "tempseg"
        session.model, session.proc = object(), object()
        self.assertEqual(session.load("tempseg"), (session.model, session.proc))


if __name__ == "__main__":
    unittest.main()
