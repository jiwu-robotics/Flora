"""Check where annotation results are persisted without running GPU models."""

import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from src.infer import __main__ as adapter


class OutputLocationTests(unittest.TestCase):
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
            episode = {"episode_index": 0, "length": 2}

            def commands(command, **kwargs):
                if "--validate-only" in command:
                    return SimpleNamespace(
                        returncode=0,
                        stdout=json.dumps({"cameras": {"main": {"frames": 2}}}),
                        stderr="",
                    )
                result = Path(command[command.index("--output") + 1])
                result.write_text(
                    json.dumps(
                        {"segments": [{"start_s": 0, "end_s": 1, "status": "complete"}]}
                    )
                )
                return SimpleNamespace(returncode=0)

            with (
                patch.object(
                    adapter,
                    "dataset",
                    return_value=[(episode, video, 30, "observation.images.ego_l")],
                ),
                patch.object(adapter.subprocess, "run", side_effect=commands),
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
