"""Offline checks against real Airflow/Kubernetes model classes."""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load("flora_stage", ROOT / "airflow/dags/flora_stage.py")


class BootstrapTests(unittest.TestCase):
    def test_execution_id_retains_identity_and_is_safe(self):
        value = stage.execution_id("jiwu_flora", "manual__2026-11-20T12:00:00+00:00")
        self.assertRegex(value, r"^airflow-[0-9a-f]{64}$")
        self.assertEqual(
            value, stage.execution_id("jiwu_flora", "manual__2026-11-20T12:00:00+00:00")
        )
        self.assertNotEqual(
            stage.execution_id("a:b", "c"), stage.execution_id("a", "b:c")
        )

    def test_resolver_contains_paths_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mount = root / "mount"
            mount.mkdir()
            dataset = mount / "package"
            dataset.mkdir()
            (mount / "escape").symlink_to(root, target_is_directory=True)
            with patch.dict(stage.HOST_MOUNTS, {"/mnt/sdb/jiwu-dagger": str(mount)}):
                self.assertEqual(stage.resolve_dataset("dagger", "package"), dataset)
                self.assertEqual(
                    stage.resolve_dataset("dagger", "/mnt/sdb/jiwu-dagger/package"),
                    dataset,
                )
                for value in ("..", ".", "escape", "/etc", "/mnt/sdb/jiwu-umi/package"):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        stage.resolve_dataset("dagger", value)

    def test_bootstrap_passes_shared_driver_and_persistent_artifacts(self):
        import yaml

        flow = (ROOT / "kestra/jiwu_flora.yaml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                "STAGE": "validate",
                "DATASET_KIND": "dagger",
                "DATASET_DIR": "test",
                "FLORA_DAG_ID": "jiwu_flora",
                "FLORA_RUN_ID": "manual:abc",
            }
            observed = {}

            def run(path, run_name):
                observed.update(
                    code=Path(path).read_text(), argv=list(sys.argv), run_name=run_name
                )

            original_read = Path.read_text

            def read(path, *args, **kwargs):
                if str(path) == "/app/kestra/jiwu_flora.yaml":
                    return flow
                return original_read(path, *args, **kwargs)

            with (
                patch.dict(os.environ, env),
                patch.object(stage, "resolve_dataset", return_value=root),
                patch.object(stage.os, "chdir"),
                patch.object(stage.sys, "path", list(sys.path)),
                patch.object(stage.sys, "argv", []),
                patch.object(Path, "read_text", read),
                patch.object(stage.runpy, "run_path", side_effect=run),
            ):
                stage.main()
            self.assertEqual(
                observed["code"], yaml.safe_load(flow)["variables"]["stage_driver"]
            )
            self.assertEqual(observed["argv"][1], str(root))
            self.assertEqual(
                Path(observed["argv"][2]).relative_to(root).parts[-2:],
                ("artifacts", "validate"),
            )


class DagTests(unittest.TestCase):
    def setUp(self):
        self.module = load("flora_dag", ROOT / "airflow/dags/jiwu_flora.py")
        self.dag = self.module.dag

    def test_dependencies_and_skip_gate(self):
        self.assertEqual(
            self.dag.get_task("validate").downstream_task_ids, {"inference_enabled"}
        )
        self.assertEqual(
            self.dag.get_task("annotate").upstream_task_ids, {"inference_enabled"}
        )
        self.assertFalse(self.module.inference_enabled(params={"inference": False}))
        self.assertTrue(self.module.inference_enabled(params={"inference": True}))
        self.assertEqual(self.dag.max_active_runs, 1)

    def test_parameters_reject_invalid_images_and_episodes(self):
        from airflow.exceptions import ParamValidationError

        for name, values in {
            "flora_image": ["flora:latest", "sha256:" + "a" * 64],
            "episodes": [[1, 1], [-1], [True]],
        }.items():
            for value in values:
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaises(ParamValidationError),
                ):
                    self.dag.params.get_param(name).resolve(value)

    def test_rendered_pods_use_same_node_and_only_annotate_requests_gpu(self):
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
        }
        context = {"params": params, "dag": self.dag, "run_id": "manual:example"}
        for name in ("validate", "annotate"):
            task = self.dag.get_task(name)
            task.render_template_fields(context)
            env = {item.name: item.value for item in task.env_vars}
            self.assertEqual(env["INCLUDE_FLAGS"], "true")
            self.assertEqual(json.loads(env["EPISODES_JSON"]), [1, 3])
            self.assertTrue(all(isinstance(value, str) for value in env.values()))
            self.assertEqual(task.node_selector, {"kubernetes.io/hostname": "gpu01"})
            self.assertEqual(task.image, params["flora_image"])
            self.assertEqual(task.image_pull_policy, "Never")
            self.assertFalse(task.do_xcom_push)
            self.assertFalse(task.automount_service_account_token)
            self.assertEqual(task.retries, 0)
            task.hook = SimpleNamespace(is_in_cluster=True)
            pod = task.build_pod_request_obj()
            self.assertEqual(pod.spec.node_selector, task.node_selector)
            self.assertEqual(
                pod.spec.runtime_class_name, "nvidia" if name == "annotate" else None
            )
            self.assertEqual(pod.spec.containers[0].resources, task.container_resources)
            self.assertEqual(pod.spec.containers[0].command, ["python", "-c"])
            self.assertFalse(pod.spec.automount_service_account_token)
            self.assertEqual(len(pod.spec.containers), 1)
            self.assertEqual(pod.spec.restart_policy, "Never")
            if name == "validate":
                self.assertNotIn("nvidia.com/gpu", task.container_resources.limits)
                self.assertIsNone(task.full_pod_spec.spec.runtime_class_name)
                self.assertNotIn("models", [v.name for v in task.volumes])
            else:
                self.assertEqual(task.container_resources.limits["nvidia.com/gpu"], "1")
                self.assertEqual(task.full_pod_spec.spec.runtime_class_name, "nvidia")
                self.assertIn("models", [v.name for v in task.volumes])


if __name__ == "__main__":
    unittest.main()
