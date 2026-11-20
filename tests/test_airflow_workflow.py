"""Offline checks for the Airflow workflow's shared stage implementation."""

import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from src.infer import airflow_stage

ROOT = Path(__file__).resolve().parents[1]


class AirflowWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("airflow"), "Airflow is not installed"
    )
    def test_dag_factory_discovers_and_builds_pods(self):
        from dagfactory import load_yaml_dags

        scope = {}
        load_yaml_dags(
            globals_dict=scope,
            config_filepath=str(ROOT / "dag/airflow/jiwu_flora.yaml"),
        )
        dag = scope["jiwu_flora"]
        self.assertEqual(
            dag.get_task("validate").downstream_task_ids, {"inference_enabled"}
        )
        self.assertEqual(
            dag.get_task("annotate").upstream_task_ids, {"inference_enabled"}
        )
        gate = dag.get_task("inference_enabled")
        for enabled, expected in ((True, 0), (False, 99)):
            command = (
                dag.get_template_env()
                .from_string(gate.bash_command)
                .render(params={"inference": enabled})
            )
            self.assertEqual(
                subprocess.run(["bash", "-c", command], check=False).returncode,
                expected,
            )
        self.assertIn(99, gate.skip_on_exit_code)
        params = {
            "flora_image": "registry.example/flora@sha256:" + "a" * 64,
            "node_name": "gpu01",
            "dataset_dir": "package",
            "dataset": "dagger",
            "dataset_key": "",
            "episodes": [1, 3],
            "include_flags": True,
            "max_parts": 0,
            "model_mode": "tempseg",
            "segments_execution_id": "",
            "inference": True,
        }
        for name in ("validate", "annotate"):
            task = dag.get_task(name)
            task.render_template_fields(
                {"params": params, "dag": dag, "run_id": "manual:example"}
            )
            task.hook = SimpleNamespace(is_in_cluster=True)
            pod = task.build_pod_request_obj()
            self.assertEqual(
                pod.spec.node_selector, {"kubernetes.io/hostname": "gpu01"}
            )
            self.assertEqual(
                pod.spec.runtime_class_name,
                "nvidia" if name == "annotate" else None,
            )
            self.assertEqual(len(pod.spec.volumes), 5 if name == "annotate" else 4)
            self.assertEqual(
                pod.spec.containers[0].command,
                ["python", "-m", "src.infer.airflow_stage"],
            )

    def test_embedded_kestra_driver_matches_image_module(self):
        flow = yaml.safe_load((ROOT / "dag/kestra/jiwu_flora.yaml").read_text())

        def normalized(source):
            tree = ast.parse(source)
            imports = sorted(
                ast.dump(node)
                for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
            body = [
                ast.dump(node)
                for node in tree.body
                if not isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            return imports, body

        self.assertEqual(
            normalized((ROOT / "src/infer/workflow_stage.py").read_text()),
            normalized(flow["variables"]["stage_driver"]),
        )

    def test_bootstrap_passes_stage_and_artifact_directory(self):
        env = {
            "STAGE": "validate",
            "DATASET_KIND": "dagger",
            "DATASET_DIR": "package",
            "FLORA_DAG_ID": "jiwu_flora",
            "FLORA_RUN_ID": "manual:abc",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observed = {}

            def run(module, run_name):
                observed.update(module=module, argv=list(sys.argv), run_name=run_name)

            with (
                patch.dict(os.environ, env),
                patch.object(airflow_stage, "resolve_dataset", return_value=root),
                patch.object(airflow_stage.os, "chdir"),
                patch.object(airflow_stage.sys, "path", list(sys.path)),
                patch.object(airflow_stage.sys, "argv", []),
                patch.object(airflow_stage.runpy, "run_module", side_effect=run),
            ):
                airflow_stage.main()
            self.assertEqual(observed["module"], "src.infer.workflow_stage")
            self.assertEqual(observed["argv"][1], str(root))
            self.assertEqual(
                Path(observed["argv"][2]).relative_to(root).parts[-2:],
                ("artifacts", "validate"),
            )


if __name__ == "__main__":
    unittest.main()
