"""Check where annotation results are persisted without running GPU models."""

import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from src.infer import __main__ as adapter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "captioner"))
from batch_utils.api import DataEnginePipeline


class OutputLocationTests(unittest.TestCase):
    def test_umi_duration_limit_uses_probed_duration(self):
        args = SimpleNamespace(kind="umi", episode=None, max_parts=1)
        episode = {"episode_index": 0, "length": 2}
        video = Path("/tmp/episode.mp4")
        for duration in (90, 90.01):
            checked = SimpleNamespace(
                duration_s=duration,
                sha256="abc",
                rate=30,
                pts_us=(0, 33_333),
                size=(16, 16),
                cfr=True,
            )
            with (
                self.subTest(duration=duration),
                patch.object(
                    adapter, "dataset", return_value=[(episode, video, 30, "ego_l")]
                ),
                patch.object(
                    DataEnginePipeline,
                    "_inputs",
                    return_value=({"main": checked}, "Human"),
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                parts = adapter.prepare_video_parts(
                    args, Path("/tmp"), "tempseg", Path("/tmp"), None
                )
                if duration <= 90:
                    self.assertEqual(len(list(parts)), 1)
                else:
                    with self.assertRaisesRegex(ValueError, "exceeds 90 seconds"):
                        list(parts)

    def test_default_runs_are_separate_and_contain_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "episode.mp4"
            video.touch()
            args = SimpleNamespace(
                dataset=root,
                kind="umi",
                episode=None,
                max_parts=1,
                output=None,
                run=True,
            )
            job = {"id": "episode_000000", "offset_s": 0, "start_frame": 0}

            def stages(args, mode, output, parts):
                for entry, *_ in parts:
                    adapter.write_episode_result(
                        output,
                        entry,
                        {
                            "segments": [
                                {"start_s": 0, "end_s": 1, "status": "complete"}
                            ]
                        },
                        captions=True,
                    )
                return [job]

            with (
                patch.object(
                    adapter,
                    "prepare_video_parts",
                    side_effect=lambda *args: iter([(job,)]),
                ),
                patch.object(adapter, "run_video_stages", side_effect=stages),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                adapter.run(args)
                adapter.run(args)

            runs = list((root / "flora_annotations").iterdir())
            self.assertEqual(len(runs), 2)
            for run in runs:
                self.assertTrue((run / "manifest.json").is_file())
                result = json.loads((run / "episode_000000.json").read_text())
                self.assertEqual(result["segments"][0]["status"], "complete")

    def test_explicit_output_does_not_overwrite_existing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "chosen"
            output.mkdir()
            manifest = output / "manifest.json"
            manifest.write_text("existing")
            args = SimpleNamespace(dataset=root, output=output)
            with self.assertRaises(FileExistsError):
                adapter.run(args)
            self.assertEqual(manifest.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
