"""Native results contract tests: CPU fixtures, no checkpoint downloads."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "captioner"))
from src.infer.results import Results, snapshot, verify_row_clock


class NativeResultsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "meta").mkdir()
        (self.root / "meta/info.json").write_text("{}")
        (self.root / "meta/episodes.jsonl").write_text("{}\n")
        self.path = self.root / "data/chunk-007/episode_000000.parquet"
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"fixture")
        self.output = self.root / "out"
        self.output.mkdir()
        self.args = SimpleNamespace(
            kind="dagger",
            episode=None,
            max_parts=0,
            run=True,
            direct_parquet=True,
            include_flags=True,
            flag_merge_gap=30,
            dataset_key="source-id",
            weights_path=None,
            instruction="",
            resume=False,
        )
        self.episodes = [({"episode_index": 0, "length": 100}, self.path, 4, "cam")]
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def collector(self):
        return Results(
            self.args,
            self.root,
            self.output,
            self.episodes,
            snapshot(self.root, ["meta/info.json", "meta/episodes.jsonl"]),
        )

    def part(self, start, count, segments=()):
        job = {
            "id": f"part-{start}",
            "episode_index": 0,
            "start_frame": start,
            "frames": count,
            "offset_s": start / 4,
        }
        video = SimpleNamespace(
            sha256="abc",
            duration_s=count / 4,
            pts_us=tuple(i * 250000 for i in range(count)),
        )
        result = {
            "input_sha256": {"main": "abc"},
            "segments": [
                {
                    "start_frame": a,
                    "end_frame": b,
                    "start_s": a / 4,
                    "end_s": b / 4,
                    "segmentation_provenance": "fine",
                }
                for a, b in segments
            ],
        }
        return job, video, result

    def read(self):
        doc = json.loads((self.output / "results.json").read_text())
        try:
            import jsonschema
        except ImportError:
            pass
        else:
            schema = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "src/infer/results.schema.json"
                ).read_text()
            )
            jsonschema.Draft202012Validator(schema).validate(doc)
        return doc, doc["results"]["source-id"]["chunk-007"]["0"]

    def test_direct_parquet_preserves_distinct_recording_clock(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.table({
            "frame_index": [0, 1, 2], "episode_index": [0, 0, 0],
            "relative_timestamp_sec": [0.0, 0.25, 0.5],
            "timestamp": [100.0, 100.25, 100.75],
        }), self.path)
        video = SimpleNamespace(pts_us=(0, 250000, 500000))
        verify_row_clock(self.path, 0, 3, video, direct_parquet=True)
        with self.assertRaisesRegex(ValueError, "presentation PTS"):
            verify_row_clock(self.path, 0, 3, video)

    def test_complete_empty_detection_and_episode_flags(self):
        collector = self.collector()
        collector.add(*self.part(0, 50, [(0, 49)]))
        collector.add(*self.part(50, 50, [(51, 100)]))
        collector.write()
        doc, row = self.read()
        self.assertTrue(doc["complete"])
        self.assertEqual(row["flags"], [50])
        self.assertEqual(
            row["processed_ranges"], [{"start_frame": 0, "end_frame": 100}]
        )
        self.assertEqual([s["part_id"] for s in row["segments"]], ["part-0", "part-50"])
        self.assertNotIn(str(self.root), json.dumps(doc))
        collector.entries[0]["segments"] = []
        collector.write()
        self.assertTrue(self.read()[0]["complete"])

    def test_partial_unprocessed_and_validation(self):
        second = self.path.with_name("episode_000001.parquet")
        second.write_bytes(b"second")
        self.episodes.append(({"episode_index": 1, "length": 100}, second, 4, "cam"))
        collector = self.collector()
        collector.add(*self.part(0, 50))
        collector.write()
        doc, row = self.read()
        self.assertFalse(doc["complete"])
        self.assertEqual(row["status"], "partial")
        self.assertEqual(
            doc["results"]["source-id"]["chunk-007"]["1"]["status"], "not_processed"
        )
        self.assertEqual(len(doc["selection"]["episodes"]), 2)

    def test_validation_never_counts_as_inference(self):
        self.args.run = False
        self.args.include_flags = False
        collector = self.collector()
        collector.add(*self.part(0, 100)[:2])
        collector.write()
        doc, row = self.read()
        self.assertFalse(doc["complete"])
        self.assertEqual(row["status"], "validated")
        self.assertEqual(row["processed_ranges"], [])
        self.assertNotIn("flags", row)

    def test_duplicate_overlap_wrong_frames_and_nonfinite_rejected(self):
        collector = self.collector()
        collector.add(*self.part(0, 50))
        for item in (self.part(0, 50), self.part(40, 60)):
            with self.assertRaises(ValueError):
                collector.add(*item)
        for value in (float("nan"), float("inf"), -1, 1000):
            job, video, result = self.part(50, 50, [(51, 80)])
            result["segments"][0]["end_s"] = value
            with self.assertRaises(ValueError):
                collector.add(job, video, result)
        job, video, result = self.part(50, 50, [(51, 80)])
        result["segments"][0]["start_frame"] = 1
        with self.assertRaises(ValueError):
            collector.add(job, video, result)

    def test_mutation_and_failure_are_not_publishable(self):
        collector = self.collector()
        collector.add(*self.part(0, 100))
        self.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            collector.write()
        doc, row = self.read()
        self.assertFalse(doc["complete"])
        self.assertEqual(row["error"]["code"], "source_changed")
        self.assertNotIn(str(self.root), row["error"]["message"])

    def test_resume_checks_effective_parameters_and_rebuilds(self):
        collector = self.collector()
        collector.add(*self.part(0, 100))
        collector.write()
        self.args.resume = True
        resumed = self.collector()
        self.assertFalse((self.output / "results.json").exists())
        resumed.write()
        self.assertFalse(self.read()[0]["complete"])
        self.args.max_parts = 1
        with self.assertRaisesRegex(ValueError, "resume identity"):
            self.collector()
        self.assertFalse((self.output / "results.json").exists())

    def test_atomic_failure_and_size_limit(self):
        from src.infer.direct import atomic_json

        path = self.output / "atomic.json"
        atomic_json(path, {"original": True})
        with self.assertRaises(ValueError):
            atomic_json(path, {"bad": float("nan")})
        self.assertEqual(json.loads(path.read_text()), {"original": True})
        self.assertEqual(list(self.output.glob(".flora-*")), [])
        collector = self.collector()
        with (
            patch("src.infer.results.MAX_RESULT_BYTES", 10),
            self.assertRaisesRegex(ValueError, "8 MiB"),
        ):
            collector.write()
        self.assertFalse((self.output / "results.json").exists())

    def test_escape_and_changed_metadata_rejected(self):
        with self.assertRaises(ValueError):
            snapshot(self.root, ["../escape"])
        link = self.root / "link"
        link.symlink_to("/etc/hosts")
        with self.assertRaises(ValueError):
            snapshot(self.root, [link])
        meta = snapshot(self.root, ["meta/info.json", "meta/episodes.jsonl"])
        (self.root / "meta/info.json").write_text('{"fps": 4}')
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            Results(self.args, self.root, self.output, self.episodes, meta)

    def test_custom_model_identity_is_content_based(self):
        from src.infer.results import model_identity

        weights = self.root / "weights"
        weights.mkdir()
        (weights / "model.safetensors").write_bytes(b"weights")
        identity, _ = model_identity(weights)
        self.assertEqual(identity["tempseg"]["kind"], "custom_merged")
        self.assertNotIn("tempseg_base", identity)
        (weights / "model.safetensors").write_bytes(b"changed")
        self.assertNotEqual(identity, model_identity(weights)[0])

    def test_failed_execution_and_code_change_cannot_complete(self):
        collector = self.collector()
        collector.add(*self.part(0, 100))
        collector.write(failed=True)
        doc, row = self.read()
        self.assertFalse(doc["complete"])
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error"]["code"], "execution_failed")
        with (
            patch("src.infer.results.code_identity", return_value="sha256:" + "0" * 64),
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            collector.write()
        self.assertFalse(self.read()[0]["complete"])

    def test_atomic_replace_failure_preserves_prior_bytes(self):
        from src.infer.direct import atomic_json

        path = self.output / "atomic.json"
        atomic_json(path, {"before": True})
        with (
            patch("src.infer.direct.os.replace", side_effect=OSError("interrupted")),
            self.assertRaises(OSError),
        ):
            atomic_json(path, {"after": True})
        self.assertEqual(json.loads(path.read_text()), {"before": True})
        self.assertFalse(list(self.output.glob(".flora-*")))

    def test_nonconsecutive_episode_selection_rejects_missing_indices(self):
        from src.infer.__main__ import dataset

        info = {
            "fps": 30,
            "chunks_size": 10,
            "features": {"observation.images.high_cam": {"dtype": "image"}},
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        }
        (self.root / "meta/info.json").write_text(json.dumps(info))
        (self.root / "meta/episodes.jsonl").write_text(
            "\n".join(
                json.dumps({"episode_index": i, "length": 10}) for i in [0, 9, 19, 29]
            )
        )
        for i in [9, 19, 29]:
            path = self.root / f"data/chunk-{i // 10:03d}/episode_{i:06d}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        selected = list(dataset(self.root, "dagger", [9, 19, 29]))
        self.assertEqual([ep["episode_index"] for ep, *_ in selected], [9, 19, 29])
        self.assertEqual(
            [p.parent.name for _, p, *_ in selected],
            ["chunk-000", "chunk-001", "chunk-002"],
        )
        with self.assertRaisesRegex(ValueError, "missing"):
            list(dataset(self.root, "dagger", [9, 17]))

    def test_decimal_episode_end_is_not_compared_to_binary_float(self):
        self.episodes[0][0]["length"] = 182
        collector = self.collector()
        job = {
            "id": "part-0",
            "episode_index": 0,
            "start_frame": 0,
            "frames": 182,
            "offset_s": 0.0,
        }
        video = SimpleNamespace(
            sha256="abc",
            duration_s=6.066667,
            pts_us=tuple(Fraction(i * 1000000, 30) for i in range(182)),
        )
        result = {
            "input_sha256": {"main": "abc"},
            "segments": [
                {
                    "start_s": 0.0,
                    "end_s": 6.066667,
                    "start_frame": 0,
                    "end_frame": 182,
                    "segmentation_provenance": "fine",
                }
            ],
        }
        collector.add(job, video, result)
        collector.write()
        self.assertTrue(self.read()[0]["complete"])

    def test_native_noninteger_boundary_and_overlap_preserved(self):
        from batch_utils.segment_output import frame_span

        from src.infer.results import local_time

        video = SimpleNamespace(pts_us=(0, 200000, 500000, 750000), duration_s=1)
        self.assertEqual(frame_span(video, 0.3, 0.75), (1, 3))
        self.assertEqual(frame_span(video, 0.3, 0.31), (1, 2))
        self.assertEqual(local_time(60 + 0.2, 60, video), Fraction(1, 5))
        collector = self.collector()
        collector.add(*self.part(0, 100, [(0, 80), (40, 100)]))
        collector.write()
        self.assertEqual(len(self.read()[1]["segments"]), 2)

    def test_direct_validation_selection_survives_max_parts(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            from PIL import Image
        except ImportError:
            self.skipTest("pyarrow and Pillow required")
        from batch_utils import dataset as reader

        from src.infer import __main__ as adapter

        info = {
            "fps": 4,
            "chunks_size": 1,
            "features": {"observation.images.high_cam": {"dtype": "image"}},
            "data_path": "data/chunk-007/episode_{episode_index:06d}.parquet",
        }
        (self.root / "meta/info.json").write_text(json.dumps(info))
        (self.root / "meta/episodes.jsonl").write_text(
            "\n".join(json.dumps({"episode_index": i, "length": 12}) for i in range(2))
        )
        buffer = io.BytesIO()
        Image.new("RGB", (16, 16)).save(buffer, format="JPEG")
        for index in range(2):
            pq.write_table(
                pa.Table.from_pylist(
                    [
                        {
                            "episode_index": index,
                            "frame_index": i,
                            "relative_timestamp_sec": 10 + i / 4,
                            "observation.images.high_cam": {"bytes": buffer.getvalue()},
                        }
                        for i in range(12)
                    ]
                ),
                self.path.with_name(f"episode_{index:06d}.parquet"),
            )
        self.args.dataset, self.args.output = self.root, self.output
        self.args.mode, self.args.run, self.args.max_parts = "tempseg", False, 1
        with patch.object(reader, "MAX_FRAME_COUNT", 5):
            adapter.run(self.args)
        doc, row = self.read()
        self.assertEqual(row["status"], "not_processed")
        self.assertEqual(len(doc["selection"]["episodes"]), 2)
        self.assertEqual(row["processed_ranges"], [])
        self.assertFalse(doc["complete"])
        self.assertFalse(list(self.output.glob("*.avi")))

    def test_native_video_validation_umi_end_to_end(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("pyarrow required")
        from batch_utils.api import DataEnginePipeline

        from src.infer import __main__ as adapter
        from src.infer.results import digest

        info = {
            "fps": 4,
            "chunks_size": 1,
            "features": {"observation.images.ego_l": {"dtype": "video"}},
            "data_path": "data/chunk-007/episode_{episode_index:06d}.parquet",
            "video_path": "videos/chunk-007/{video_key}/episode_{episode_index:06d}.mp4",
        }
        (self.root / "meta/info.json").write_text(json.dumps(info))
        (self.root / "meta/episodes.jsonl").write_text(
            json.dumps({"episode_index": 0, "length": 4})
        )
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {"episode_index": 0, "frame_index": i, "timestamp": t}
                    for i, t in enumerate([10.0, 10.2, 10.5, 10.75])
                ]
            ),
            self.path,
        )
        path = (
            self.root / "videos/chunk-007/observation.images.ego_l/episode_000000.mp4"
        )
        path.parent.mkdir(parents=True)
        path.write_bytes(b"mock decoded video")
        video = SimpleNamespace(
            pts_us=(0, 200000, 500000, 750000),
            duration_s=1,
            sha256=digest(path),
            rate=4,
            size=(16, 16),
            cfr=False,
        )
        self.args.kind, self.args.run, self.args.direct_parquet = "umi", False, False
        self.args.mode = "tempseg"
        self.args.dataset, self.args.output = self.root, self.output
        with patch.object(
            DataEnginePipeline, "_inputs", return_value=({"main": video}, "Human")
        ):
            adapter.run(self.args)
        doc, row = self.read()
        self.assertEqual(row["status"], "validated")
        self.assertEqual(len(row["source"]["files"]), 4)
        self.assertFalse(doc["complete"])

    def test_umi_irregular_pts_and_clock_mismatch(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest("pyarrow required")
        rows = [
            {"episode_index": 0, "frame_index": i, "timestamp": t}
            for i, t in enumerate([10.0, 10.2, 10.5, 10.75])
        ]
        pq.write_table(pa.Table.from_pylist(rows), self.path)
        video = SimpleNamespace(pts_us=(0, 200000, 500000, 750000))
        verify_row_clock(self.path, 0, 4, video)
        video.pts_us = (0, 250000, 500000, 750000)
        with self.assertRaisesRegex(ValueError, "presentation PTS"):
            verify_row_clock(self.path, 0, 4, video)
        rows[1]["frame_index"] = 2
        pq.write_table(pa.Table.from_pylist(rows), self.path)
        with self.assertRaises(ValueError):
            verify_row_clock(self.path, 0, 4, video)


if __name__ == "__main__":
    unittest.main()
