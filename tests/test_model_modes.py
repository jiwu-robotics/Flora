"""Exercise dataset stage ordering and safe reuse of TempSeg results without a GPU."""

import contextlib
from fractions import Fraction
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.infer import __main__ as adapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "captioner"))
from batch_utils.api import DataEnginePipeline
from caption_only import checked_segments


class SegmentValidationTests(unittest.TestCase):
    def test_segment_validation_checks_identity_and_intervals(self):
        inspection = {
            "profile": "Human",
            "duration_s": 4,
            "cameras": {"main": {"sha256": "abc"}},
        }
        source = {
            "schema_version": "flora_tempseg_v1",
            "input_sha256": {"main": "abc"},
            "profile": "Human",
            "segments": [{"start_s": 1, "end_s": 2}],
        }
        self.assertEqual(checked_segments(source, inspection)[0]["start_s"], 1)
        source["input_sha256"]["main"] = "wrong"
        with self.assertRaisesRegex(ValueError, "hashes"):
            checked_segments(source, inspection)
        source["input_sha256"]["main"] = "abc"
        source["segments"][0]["end_s"] = 9
        with self.assertRaisesRegex(ValueError, "interval"):
            checked_segments(source, inspection)


def fake_video(path):
    return SimpleNamespace(
        path=Path(path),
        sha256=Path(path).stem,
        rate=Fraction(4),
        pts_us=tuple(range(0, 2_000_000, 250_000)),
        duration_s=2,
        size=(16, 16),
        cfr=True,
    )


@unittest.skipUnless(
    all(importlib.util.find_spec(name) for name in ("torch", "av", "PIL")),
    "Stage scheduling tests require the annotation environment",
)
class ModelModesTests(unittest.TestCase):
    def setUp(self):
        from batch_utils import models, pipeline

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = []
        self.loaded = None
        self.first_inference = None
        self.files = [self.root / f"episode_{i:06d}.mp4" for i in range(2)]
        self.episodes = [
            ({"episode_index": i, "length": 8}, path, 4, "cam")
            for i, path in enumerate(self.files)
        ]
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.enterContext(patch("torch.cuda.is_available", return_value=True))
        self.factory = self.enterContext(
            patch.object(models, "Session", side_effect=self.make_session)
        )
        self.enterContext(patch.object(pipeline, "segment", side_effect=self.segment))
        self.enterContext(
            patch.object(pipeline, "caption_single", side_effect=self.caption)
        )

    def make_session(self, **kwargs):
        def load(kind):
            if session.kind is None:
                self.assertIsNone(self.loaded, "previous stage is still resident")
                self.loaded = session.kind = kind
                self.events.append(("load", kind))
            self.assertEqual(session.kind, kind)
            self.assertEqual(threading.current_thread().name, "MainThread")

        def close():
            self.events.append(("close", session.kind))
            self.loaded = None

        session = SimpleNamespace(kind=None, load=load, close=close)
        return session

    def segment(self, videos, pool, session, instruction, progress):
        session.load("tempseg")
        self.events.append(("segment", videos["main"].sha256))
        if self.first_inference:
            self.first_inference()
        return [
            dict(start_s=0.25, end_s=1.5, metadata={"segmentation_provenance": "fine"})
        ], [{"window_index": 0}]

    def caption(self, videos, segments, profile, session, instruction, progress):
        session.load("captioner")
        self.events.append(("caption", videos["main"].sha256))
        if self.first_inference:
            self.first_inference()
        rows = [
            dict(
                start_s=s["start_s"],
                end_s=s["end_s"],
                caption="Pick up the cup.",
                status="complete",
            )
            for s in segments
        ]
        return rows, [{"event_id": "event_0"}]

    def test_video_modes_reuse_one_session_per_stage_and_keep_episode_clock(self):
        for kind in ("umi", "dagger"):
            for mode in ("both", "tempseg", "captioner"):
                with self.subTest(kind=kind, mode=mode):
                    self.events.clear()
                    self.factory.reset_mock()
                    prior = self.root / f"prior-{kind}-{mode}"
                    prior.mkdir()
                    output = self.root / f"out-{kind}-{mode}"
                    ids = [p.stem for p in self.files]
                    offset = 0 if kind == "umi" else 2.5
                    if kind == "dagger":
                        ids = [f"{name}_part_0001" for name in ids]
                    profile = "YAM" if kind == "dagger" else "Human"
                    ready = threading.Event()

                    def prepared(path, episode, fps, key, media, remaining):
                        yield {
                            "id": ids[episode["episode_index"]],
                            "video": str(path),
                            "start_frame": int(offset * fps),
                            "frames": 8,
                            "offset_s": offset,
                        }

                    def inputs(path, **kwargs):
                        if Path(path) == self.files[1]:
                            ready.set()
                        return {"main": fake_video(path)}, profile

                    def check_overlap():
                        self.assertTrue(ready.wait(3), "second part was not prefetched")
                        self.first_inference = None

                    self.first_inference = check_overlap
                    for i, path in enumerate(self.files):
                        (prior / f"{ids[i]}.json").write_text(
                            json.dumps(
                                {
                                    "schema_version": "flora_tempseg_v1",
                                    "profile": profile,
                                    "model_revisions": {},
                                    "input_sha256": {"main": path.stem},
                                    "segments": [
                                        {
                                            "start_s": offset + 0.25,
                                            "end_s": offset + 1.5,
                                        }
                                    ],
                                    "episode_source": {
                                        "episode_index": i,
                                        "start_frame": int(offset * 4),
                                        "frames": 8,
                                        "fps": 4,
                                        "camera": "cam",
                                        "source": str(path),
                                    },
                                }
                            )
                        )
                    args = SimpleNamespace(
                        dataset=self.root,
                        output=output,
                        kind=kind,
                        episode=None,
                        max_parts=0,
                        run=True,
                        mode=mode,
                        segments_dir=prior if mode == "captioner" else None,
                        include_flags=mode == "tempseg",
                        flag_merge_gap=0,
                    )
                    with (
                        patch.object(adapter, "dataset", return_value=self.episodes),
                        patch("src.infer.results.snapshot", return_value=[]),
                        patch("src.infer.results.Results"),
                        patch.object(adapter, "dagger_parts", side_effect=prepared),
                        patch.object(DataEnginePipeline, "_inputs", side_effect=inputs),
                    ):
                        adapter.run(args)
                    expected = self.stage_events(mode)
                    self.assertEqual(self.events, expected)
                    self.assertEqual(
                        self.factory.call_count, 2 if mode == "both" else 1
                    )
                    manifest = json.loads((output / "manifest.json").read_text())
                    self.assertEqual(manifest["mode"], mode)
                    self.assertEqual([item["id"] for item in manifest["parts"]], ids)
                    for i, name in enumerate(ids):
                        result = json.loads((output / f"{name}.json").read_text())
                        segment = result["segments"][0]
                        self.assertEqual(segment["start_s"], offset + 0.25)
                        self.assertEqual(segment["end_s"], offset + 1.5)
                        self.assertEqual(result["episode_source"]["episode_index"], i)
                        if mode == "tempseg":
                            self.assertEqual(
                                segment["start_frame"], int(offset * 4) + 1
                            )
                            self.assertEqual(result["flags"], [])
                        else:
                            self.assertEqual(segment["status"], "complete")
                    if mode == "both":
                        checkpoint = adapter.read_segments(
                            output / "segments", manifest["parts"][0]
                        )
                        self.assertEqual(checkpoint["segments"][0]["start_s"], 0.25)

    def stage_events(self, mode):
        expected = []
        if mode in ("both", "tempseg"):
            expected.append(("load", "tempseg"))
            expected.extend(("segment", path.stem) for path in self.files)
            expected.append(("close", "tempseg"))
        if mode in ("both", "captioner"):
            expected.append(("load", "captioner"))
            expected.extend(("caption", path.stem) for path in self.files)
            expected.append(("close", "captioner"))
        return expected

    def test_jsonl_runs_all_tempseg_jobs_before_captioning_and_preserves_audit(self):
        from batch_utils import cli

        source = self.root / "jobs.jsonl"
        output = self.root / "out"
        source.write_text(
            "\n".join(json.dumps({"id": p.stem, "video": p.name}) for p in self.files)
        )
        with patch.object(
            DataEnginePipeline,
            "_inputs",
            side_effect=lambda video: ({"main": fake_video(video)}, "Human"),
        ):
            exit_code = cli.main(
                [
                    "--input-jsonl",
                    str(source),
                    "--output-dir",
                    str(output),
                    "--include-audit",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(self.events, self.stage_events("both"))
        for path in self.files:
            result = json.loads((output / f"{path.stem}.json").read_text())
            self.assertEqual(result["input_sha256"], {"main": path.stem})
            self.assertEqual(
                result["pipeline"]["temporal_windows"], [{"window_index": 0}]
            )
            self.assertEqual(
                result["pipeline"]["caption_inputs"], [{"event_id": "event_0"}]
            )

    def test_jsonl_changed_source_stops_before_captioning(self):
        from batch_utils import cli

        path = self.files[0]
        source = self.root / "jobs.jsonl"
        source.write_text(json.dumps({"video": path.name}))
        output = self.root / "out"
        original = fake_video(path)
        updated = fake_video(path)
        updated.sha256 = "changed"
        with patch.object(
            DataEnginePipeline,
            "_inputs",
            side_effect=[({"main": original}, "Human"), ({"main": updated}, "Human")],
        ):
            exit_code = cli.main(
                ["--input-jsonl", str(source), "--output-dir", str(output)]
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            self.events,
            [
                ("load", "tempseg"),
                ("segment", path.stem),
                ("close", "tempseg"),
                ("close", None),
            ],
        )
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
