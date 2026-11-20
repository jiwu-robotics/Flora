"""Flora on k3s: CPU preflight, then optional single-GPU inference."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.sdk import DAG, Param
from kubernetes.client import models as k8s

BOOTSTRAP = Path(__file__).with_name("flora_stage.py").read_text()
# Kubernetes images use a repository digest, not a Docker-local image ID.
IMAGE_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[0-9a-f]{64}$"
DATA_MOUNTS = [
    ("dagger", "/mnt/sdb/jiwu-dagger", "/data/jiwu-dagger"),
    ("umi", "/mnt/sdb/jiwu-umi", "/data/jiwu-umi"),
    ("datasets", "/mnt/sdb/datasets", "/data/datasets"),
    ("debug", "/home/eisoc/data/debug_datapilot", "/data/debug_datapilot"),
]


def inference_enabled(**context):
    return context["params"]["inference"]


def stage_pod(stage):
    gpu = stage == "annotate"
    mounts = list(DATA_MOUNTS)
    if gpu:
        mounts.append(("models", "/mnt/sdb/.datapilot-modelzoo", "/model_zoo"))
    requests = {"cpu": "2", "memory": "8Gi"}
    limits = {"cpu": "8", "memory": "32Gi"}
    if gpu:
        requests.update({"memory": "24Gi", "nvidia.com/gpu": "1"})
        limits.update({"memory": "64Gi", "nvidia.com/gpu": "1"})
    env = {
        "STAGE": stage,
        "FLORA_IMAGE": "{{ params.flora_image }}",
        "DATASET_KIND": "{{ params.dataset }}",
        "DATASET_DIR": "{{ params.dataset_dir }}",
        "DATASET_KEY": "{{ params.dataset_key }}",
        "EPISODES_JSON": "{{ params.episodes | tojson }}",
        "INCLUDE_FLAGS": "{{ 'true' if params.include_flags else 'false' }}",
        "MAX_PARTS": "{{ params.max_parts }}",
        "MODEL_MODE": "{{ params.model_mode }}",
        "SEGMENTS_EXECUTION_ID": "{{ params.segments_execution_id }}",
        "FLORA_DAG_ID": "{{ dag.dag_id }}",
        "FLORA_RUN_ID": "{{ run_id }}",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    if gpu:
        env.update(
            FLORA_MODEL_CACHE="/model_zoo/flora/models",
            HF_HOME="/model_zoo/huggingface",
        )
    return KubernetesPodOperator(
        task_id=stage,
        name=f"flora-{stage}",
        namespace="flora",
        kubernetes_conn_id=None,
        in_cluster=True,
        image="{{ params.flora_image }}",
        image_pull_policy="Never",
        cmds=["python", "-c"],
        arguments=[BOOTSTRAP],
        env_vars=env,
        labels={"app.kubernetes.io/name": "flora", "flora-stage": stage},
        node_selector={"kubernetes.io/hostname": "{{ params.node_name }}"},
        service_account_name="flora-task",
        automount_service_account_token=False,
        security_context={"runAsUser": 0, "runAsGroup": 0},
        container_security_context={
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        },
        volumes=[
            k8s.V1Volume(
                name=name,
                host_path=k8s.V1HostPathVolumeSource(path=host, type="Directory"),
            )
            for name, host, _ in mounts
        ],
        volume_mounts=[
            k8s.V1VolumeMount(name=name, mount_path=target)
            for name, _, target in mounts
        ],
        container_resources=k8s.V1ResourceRequirements(
            requests=requests, limits=limits
        ),
        full_pod_spec=k8s.V1Pod(
            spec=k8s.V1PodSpec(
                containers=[k8s.V1Container(name="base")],
                runtime_class_name="nvidia" if gpu else None,
            )
        ),
        get_logs=True,
        log_events_on_failure=True,
        do_xcom_push=False,
        deferrable=False,
        reattach_on_restart=True,
        on_finish_action="delete_pod",
        startup_timeout_seconds=600,
        schedule_timeout_seconds=900,
        active_deadline_seconds=86400 if gpu else 7200,
        execution_timeout=timedelta(hours=25 if gpu else 3),
        termination_grace_period=60,
        retries=0,
    )


with DAG(
    dag_id="jiwu_flora",
    description="Validate Jiwu data and publish complete native Flora results on k3s",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["flora", "k3s", "gpu"],
    params={
        "flora_image": Param(
            type="string",
            pattern=IMAGE_PATTERN,
            description="Preloaded containerd repository@sha256 digest",
        ),
        "node_name": Param(
            type="string",
            minLength=1,
            pattern=r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$",
            description="Exact kubernetes.io/hostname label of the data/GPU node",
        ),
        "dataset_dir": Param(type="string", minLength=1),
        "dataset": Param("umi", enum=["dagger", "umi"]),
        "dataset_key": Param("", type="string"),
        "episodes": Param(
            [], type="array", items={"type": "integer", "minimum": 0}, uniqueItems=True
        ),
        "include_flags": Param(True, type="boolean"),
        "max_parts": Param(0, type="integer", minimum=0),
        "inference": Param(True, type="boolean"),
        "model_mode": Param("tempseg", enum=["both", "tempseg", "captioner"]),
        "segments_execution_id": Param("", type="string"),
    },
) as dag:
    validate = stage_pod("validate")
    should_annotate = ShortCircuitOperator(
        task_id="inference_enabled",
        python_callable=inference_enabled,
        retries=0,
    )
    annotate = stage_pod("annotate")
    validate >> should_annotate >> annotate
