"""Exercise stage selection and safe reuse of TempSeg results without a GPU."""

import contextlib
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
from caption_only import checked_segments


class ModelModesTests(unittest.TestCase):
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

    def test_stage_dispatch_and_reuse(self):
        for mode in ("both", "tempseg", "captioner"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                video = root / "video.mp4"
                video.touch()
                prior = root / "prior"
                prior.mkdir()
                source = {
                    "schema_version": "flora_tempseg_v1",
                    "segments": [{"start_s": 0, "end_s": 1}],
                    "episode_source": {
                        "episode_index": 0,
                        "start_frame": 0,
                        "frames": 2,
                        "fps": 30,
                        "camera": "cam",
                        "source": str(video),
                    },
                }
                (prior / "episode_000000.json").write_text(json.dumps(source))
                args = SimpleNamespace(
                    dataset=root,
                    output=root / "out",
                    kind="umi",
                    episode=None,
                    max_parts=1,
                    run=True,
                    mode=mode,
                    segments_dir=prior if mode == "captioner" else None,
                )
                calls = []

                def invoke(command, **kwargs):
                    calls.append(command)
                    if "--validate-only" in command:
                        return SimpleNamespace(
                            returncode=0,
                            stdout=json.dumps({"cameras": {"main": {"frames": 2}}}),
                            stderr="",
                        )
                    if mode == "captioner":
                        self.assertEqual(
                            json.loads(
                                Path(
                                    command[command.index("--segments") + 1]
                                ).read_text()
                            )["segments"][0]["start_s"],
                            0,
                        )
                    result = Path(command[command.index("--output") + 1])
                    result.write_text(
                        json.dumps(
                            {
                                "segments": [
                                    {
                                        "start_s": 0,
                                        "end_s": 1,
                                        **(
                                            {}
                                            if mode == "tempseg"
                                            else {"status": "complete"}
                                        ),
                                    }
                                ]
                            }
                        )
                    )
                    return SimpleNamespace(returncode=0)

                with (
                    patch.object(
                        adapter,
                        "dataset",
                        return_value=[
                            ({"episode_index": 0, "length": 2}, video, 30, "cam")
                        ],
                    ),
                    patch.object(adapter.subprocess, "run", side_effect=invoke),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    adapter.run(args)
                expected = {
                    "both": "infer.py",
                    "tempseg": "tempseg_infer.py",
                    "captioner": "caption_only.py",
                }[mode]
                self.assertEqual(Path(calls[1][1]).name, expected)
                self.assertEqual(
                    json.loads((root / "out" / "manifest.json").read_text())["mode"],
                    mode,
                )

    def test_prefetches_next_episode_during_inference_for_all_video_modes(self):
        for kind in ("umi", "dagger"):
            for mode in ("both", "tempseg", "captioner"):
                with (
                    self.subTest(kind=kind, mode=mode),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    root = Path(tmp)
                    paths = [root / f"episode_{i}.mp4" for i in range(2)]
                    for path in paths:
                        path.touch()
                    episodes = [
                        ({"episode_index": i, "length": 2}, path, 30, "cam")
                        for i, path in enumerate(paths)
                    ]
                    prior = root / "prior"
                    prior.mkdir()
                    ids = [
                        f"episode_{i:06d}"
                        if kind == "umi"
                        else f"episode_{i:06d}_part_0000"
                        for i in range(2)
                    ]
                    for i in range(2):
                        (prior / (ids[i] + ".json")).write_text(
                            json.dumps(
                                {
                                    "segments": [{"start_s": 0, "end_s": 1}],
                                    "episode_source": {
                                        "episode_index": i,
                                        "start_frame": 0,
                                        "frames": 2,
                                        "fps": 30,
                                        "camera": "cam",
                                        "source": str(paths[i]),
                                    },
                                }
                            )
                        )
                    args = SimpleNamespace(
                        dataset=root,
                        output=root / "out",
                        kind=kind,
                        episode=None,
                        max_parts=0,
                        run=True,
                        mode=mode,
                        segments_dir=prior if mode == "captioner" else None,
                    )
                    second_ready = threading.Event()
                    inference_threads = []

                    def prepared(path, episode, fps, key, media, remaining):
                        i = episode["episode_index"]
                        yield {
                            "id": ids[i],
                            "video": str(path),
                            "start_frame": 0,
                            "frames": 2,
                            "offset_s": 0,
                        }

                    def invoke(command, **kwargs):
                        if "--validate-only" in command:
                            if command[command.index("--video") + 1] == str(paths[1]):
                                second_ready.set()
                            return SimpleNamespace(
                                returncode=0,
                                stdout=json.dumps({"cameras": {"main": {"frames": 2}}}),
                                stderr="",
                            )
                        inference_threads.append(threading.current_thread().name)
                        if len(inference_threads) == 1:
                            self.assertTrue(
                                second_ready.wait(3),
                                "next episode not validated during inference",
                            )
                        output = Path(command[command.index("--output") + 1])
                        output.write_text(
                            json.dumps(
                                {
                                    "segments": [
                                        {"start_s": 0, "end_s": 1, "status": "complete"}
                                    ]
                                }
                            )
                        )
                        return SimpleNamespace(returncode=0)

                    with (
                        patch.object(adapter, "dataset", return_value=episodes),
                        patch.object(adapter, "dagger_parts", side_effect=prepared),
                        patch.object(adapter.subprocess, "run", side_effect=invoke),
                        contextlib.redirect_stdout(io.StringIO()),
                    ):
                        adapter.run(args)
                    self.assertEqual(inference_threads, ["MainThread", "MainThread"])
                    manifest = json.loads((args.output / "manifest.json").read_text())
                    self.assertEqual([item["id"] for item in manifest["parts"]], ids)


if __name__ == "__main__":
    unittest.main()
