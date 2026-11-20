"""Exercise the Kestra embedded driver without a scheduler, model, or GPU."""

import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[1]
FLOW = yaml.safe_load((REPO / "kestra/jiwu_flora.yaml").read_text())
DRIVER = compile(FLOW["variables"]["stage_driver"], "kestra-stage-driver", "exec")


class KestraDriverTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.env = {
            "STAGE": "validate",
            "MODEL_MODE": "tempseg",
            "EXECUTION_ID": "test-1",
            "FLORA_IMAGE": "sha256:" + "a" * 64,
            "EPISODES_JSON": "[9, 19]",
            "DATASET_KEY": "dataset",
            "DATASET_KIND": "dagger",
            "MAX_PARTS": "1",
            "INCLUDE_FLAGS": "true",
            "SEGMENTS_EXECUTION_ID": "",
        }
        self.document = {
            "schema_version": "flora_results_v1",
            "complete": True,
            "producer": {"revision": "same"},
            "selection": {
                "dataset_key": "dataset",
                "episodes": [
                    {"chunk": "chunk-000", "episode_index": i} for i in (9, 19)
                ],
            },
            "results": {
                "dataset": {
                    "chunk-000": {
                        str(i): {
                            "status": "success",
                            "source": {"files": []},
                            "frame_count": 100,
                            "processed_ranges": [{"start_frame": 0, "end_frame": 100}],
                        }
                        for i in (9, 19)
                    }
                }
            },
        }
        self.commands = []

    def execute(self, result=None):
        def process(command, **kwargs):
            self.commands.append(command)
            output = Path(command[command.index("--output") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "manifest.json").write_text("{}")
            document = copy.deepcopy(self.document if result is None else result)
            if self.env["STAGE"] == "validate":
                document["complete"] = False
                for row in document["results"]["dataset"]["chunk-000"].values():
                    row.update(status="validated", processed_ranges=[])
            (output / "results.json").write_text(json.dumps(document))
            return type("Process", (), {"stderr": io.StringIO(), "wait": lambda _: 0})()

        artifacts = self.root / ("artifacts-" + self.env["STAGE"])
        with (
            patch.dict(os.environ, self.env),
            patch("sys.argv", ["driver", str(self.root), str(artifacts)]),
            patch("subprocess.check_output", return_value="--dataset-key --episodes"),
            patch("subprocess.Popen", side_effect=process),
        ):
            exec(DRIVER, {"__name__": "__main__"})  # noqa: S102 - exercise the checked-in YAML driver

    def test_preflight_then_complete_publication_and_arguments(self):
        self.execute()
        validation = self.commands[-1]
        self.assertEqual(validation[validation.index("--max-parts") + 1], "0")
        self.assertIn("--include-flags", validation)
        self.assertIn("--direct-parquet", validation)
        self.assertEqual(validation[-3:], ["--episodes", "9", "19"])
        self.assertFalse((self.root / "temp_seg/results.json").exists())
        self.env["STAGE"] = "annotate"
        self.execute()
        command = self.commands[-1]
        self.assertEqual(command[command.index("--max-parts") + 1], "1")
        self.assertIn("--run", command)
        self.assertEqual(
            json.loads((self.root / "temp_seg/results.json").read_text()), self.document
        )
        self.assertTrue((self.root / "artifacts-annotate/results.json").exists())
        self.assertFalse(
            (self.root / "artifacts-annotate/results.identity.json").exists()
        )

    def test_umi_validation_explicit_mode(self):
        self.env["DATASET_KIND"] = "umi"
        self.env["INCLUDE_FLAGS"] = "false"
        self.execute()
        command = self.commands[-1]
        self.assertEqual(command[command.index("--mode") + 1], "tempseg")
        self.assertNotIn("--direct-parquet", command)
        self.assertNotIn("--include-flags", command)

    def test_partial_keeps_previous_canonical(self):
        self.execute()
        canonical = self.root / "temp_seg/results.json"
        canonical.write_text("previous")
        self.env["STAGE"] = "annotate"
        partial = copy.deepcopy(self.document)
        partial["complete"] = False
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.execute(partial)
        self.assertEqual(canonical.read_text(), "previous")
        self.assertFalse((self.root / "artifacts-annotate/results.json").exists())

    def test_source_change_and_missing_coverage_refuse_publication(self):
        self.execute()
        self.env["STAGE"] = "annotate"
        for change in ({"source": {"files": ["changed"]}}, {"processed_ranges": []}):
            invalid = copy.deepcopy(self.document)
            invalid["results"]["dataset"]["chunk-000"]["9"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.execute(invalid)
            self.assertFalse((self.root / "temp_seg/results.json").exists())

    def test_no_gpu_without_preflight_and_invalid_selection(self):
        self.env["STAGE"] = "annotate"
        with self.assertRaisesRegex(ValueError, "validation must finish"):
            self.execute()
        self.assertEqual(self.commands, [])
        self.env["STAGE"] = "validate"
        for value in ("[9, 9]", "[-1]", "[true]"):
            self.env["EPISODES_JSON"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.execute()

    def test_captioner_can_reuse_legacy_execution(self):
        self.env.update(
            MODEL_MODE="captioner",
            EPISODES_JSON="[]",
            DATASET_KEY="",
            SEGMENTS_EXECUTION_ID="old-run",
        )
        previous = self.root / "tempseg/old-run"
        previous.mkdir(parents=True)
        self.execute()
        self.env["STAGE"] = "annotate"
        self.execute()
        command = self.commands[-1]
        self.assertEqual(command[command.index("--segments-dir") + 1], str(previous))
        self.assertNotIn("--include-flags", command)
        self.assertFalse((self.root / "temp_seg/results.json").exists())

    def test_tasks_keep_validation_before_gpu(self):
        validate, annotate = FLOW["tasks"]
        self.assertNotIn("runIf", validate)
        self.assertNotIn("deviceRequests", validate["taskRunner"])
        self.assertIn("inputs.inference", annotate["runIf"])
        self.assertEqual(FLOW["id"], "jiwu_flora")
        self.assertEqual(FLOW["namespace"], "flora.jiwu")


if __name__ == "__main__":
    unittest.main()
