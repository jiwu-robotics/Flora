"""Run the shared workflow stage in an Airflow task pod."""

import hashlib
import json
import os
import runpy
import sys
from pathlib import Path

HOST_MOUNTS = {
    "/mnt/sdb/jiwu-dagger": "/data/jiwu-dagger",
    "/mnt/sdb/jiwu-umi": "/data/jiwu-umi",
    "/mnt/sdb/datasets": "/data/datasets",
    "/home/eisoc/data/debug_datapilot": "/data/debug_datapilot",
}


def resolve_dataset(kind, value):
    if kind not in ("dagger", "umi") or not value:
        raise ValueError("A supported dataset kind and nonempty directory are required")
    host = Path(f"/mnt/sdb/jiwu-{kind}")
    relative = Path(value)
    if relative.is_absolute():
        allowed = [
            host,
            Path("/mnt/sdb/datasets"),
            Path("/home/eisoc/data/debug_datapilot"),
        ]
        host = next((p for p in allowed if relative.is_relative_to(p)), None)
        if host is None:
            raise ValueError("Dataset path is outside the selected host mounts")
        relative = relative.relative_to(host)
    mount = Path(HOST_MOUNTS[str(host)]).resolve(strict=True)
    root = (mount / relative).resolve(strict=True)
    if root == mount or not root.is_relative_to(mount) or not root.is_dir():
        raise ValueError("Dataset must resolve to a directory below its mount")
    return root


def execution_id(dag_id, run_id):
    # Airflow run IDs contain ':' and '+', which the shared driver rejects.
    # Hash the complete pair instead of lossy character substitution.
    identity = json.dumps([dag_id, run_id], separators=(",", ":")).encode()
    return "airflow-" + hashlib.sha256(identity).hexdigest()


def main():
    stage = os.environ["STAGE"]
    if stage not in ("validate", "annotate"):
        raise ValueError("Unsupported stage")
    root = resolve_dataset(os.environ["DATASET_KIND"], os.environ["DATASET_DIR"])
    execution = execution_id(os.environ["FLORA_DAG_ID"], os.environ["FLORA_RUN_ID"])
    os.environ["EXECUTION_ID"] = execution
    run = root / "temp_seg" / "runs" / execution
    artifacts = run / "artifacts" / stage
    if not artifacts.resolve().is_relative_to(root):
        raise ValueError("Artifact path escapes the dataset")
    os.chdir("/app")
    sys.path.insert(0, "/app")

    print(
        json.dumps(
            {"execution_id": execution, "stage": stage, "artifacts": str(artifacts)}
        ),
        flush=True,
    )
    sys.argv = ["src.infer.workflow_stage", str(root), str(artifacts)]
    runpy.run_module("src.infer.workflow_stage", run_name="__main__")
    print(
        json.dumps(
            {
                "execution_id": execution,
                "stage": stage,
                "artifacts": str(artifacts),
                "status": "success",
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
