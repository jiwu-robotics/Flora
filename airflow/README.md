# Jiwu Flora：Airflow DAG / k3s

`dags/jiwu_flora.py` 是 `kestra/jiwu_flora.yaml` 的等价 Airflow 编排，面向已经运行在 k3s
中的 Airflow。兼容基线固定为 Airflow 3.1.0、Kubernetes provider 10.8.1，见 `requirements.txt`。
本目录不安装 Airflow 服务，不修改现有 Kestra 工作流。

```text
validate（CPU Pod） → inference_enabled → annotate（单 GPU Pod）
```

`inference=false` 时 GPU 任务标为 skipped；CPU 预检始终执行全部所选 episode。
DAgger TempSeg 直接读取原生 Parquet；UMI、both、captioner 的行为与 Kestra 相同。
`include_flags` 默认 true。完整结果需通过 selection、producer、来源摘要与完整帧覆盖检查，
才原子更新数据包的 `temp_seg/results.json`；截断或失败保留上一次成功结果。

## 部署前准备

1. 在 Airflow 控制面/worker 的独立 Python 环境安装 `requirements.txt`，不要安装进 Flora
   推理环境。把整个 `dags/` 的两个文件一起发布到 Airflow DAG bundle，保留相邻位置。
   `flora_stage.py` 在 DAG 加载时作为代码传给 Pod，无需重建 Flora 镜像。
2. 在 k3s 数据/GPU 节点安装 NVIDIA 驱动、Container Toolkit 和 device plugin；确认
   `RuntimeClass/nvidia` 存在，节点 allocatable 含 `nvidia.com/gpu`。参考
   [k3s GPU 指南](https://docs.k3s.io/advanced)。只配置 Docker 的 NVIDIA runtime 不足以支持 k3s。
3. 通过 GitOps 管理 `k3s/runtime.yaml`。部署前将 RoleBinding 中的 `airflow-worker` 替换为实际
   执行 Operator 的 ServiceAccount；LocalExecutor 通常使用 scheduler 的身份。此身份需要访问
   Kubernetes API。推理 Pod 使用独立 `flora-task`，不挂载 API token。
4. 检查下表所有目录在指定节点存在。`hostPath.type=Directory` 不会自动创建目录。
   两阶段以同一个 `kubernetes.io/hostname` 标签固定节点；不能把 CPU 校验调度到另一台机器。
   当前配置适用于可信内部任务，Pod 以 UID/GID 0 运行，以兼容现有镜像和本地缓存锁文件。
5. 保持 k3s NetworkPolicy enforcement 开启。`flora-offline` 禁止推理 Pod 入站和出站；
   Hugging Face 离线环境变量也同时启用。任务 Pod 不需要联网或访问 Airflow API。
   本例关闭 XCom sidecar，避免离线环境额外拉取 sidecar 镜像。

| 宿主机目录 | Pod 内路径 | 使用阶段 |
| --- | --- | --- |
| `/mnt/sdb/jiwu-dagger` | `/data/jiwu-dagger` | 两阶段 |
| `/mnt/sdb/jiwu-umi` | `/data/jiwu-umi` | 两阶段 |
| `/mnt/sdb/datasets` | `/data/datasets` | 两阶段 |
| `/home/eisoc/data/debug_datapilot` | `/data/debug_datapilot` | 两阶段 |
| `/mnt/sdb/.datapilot-modelzoo` | `/model_zoo` | 仅 GPU |

数据与缓存可写，模型缓存需要写入 Hugging Face 锁文件。部署到其他节点时一起调整 DAG 的
挂载表和 `flora_stage.py` 的路径映射。若改用 PVC，需要两阶段访问同一份数据；此版本不假设
k3s local-path PVC 可以跨节点共享。

CPU Pod requests 为 2 CPU / 8 GiB，limits 为 8 CPU / 32 GiB；GPU Pod requests 为
2 CPU / 24 GiB / 1 GPU，limits 为 8 CPU / 64 GiB / 1 GPU。GPU 显存由模型与卡规格决定，
Kubernetes 的 GPU 数量申请不会预留特定显存。按节点内存与模型模式调整这些配置。
任务 Pod 是有限时长的批处理，不添加 HTTP 探针；退出码、Pod 状态和结果完整性决定成功。

## 镜像：k3s containerd 与 Docker 不共享镜像库

`flora_image` 必须是 **`仓库@sha256:<64 位 manifest 摘要>`**，不能填写 Docker 的
`docker image inspect .Id`（那是 config digest），也不能使用 `latest`。
镜像应含当前的 `/app/src/infer`、`/app/kestra/jiwu_flora.yaml` 和 PyYAML。
Pod bootstrap 直接执行该镜像内 YAML 的 `stage_driver`，因此完整性检查与 Kestra 使用同一实现。
换镜像也意味着更新 driver，应同时审核其中的 YAML。

先按正常镜像发布流程构建、扫描并推送到可信 registry，获取 repository digest，然后在指定
节点预载到 k3s containerd（以下值需替换）：

```bash
sudo k3s ctr -n k8s.io images pull registry.example.com/robotics/flora@sha256:<manifest-digest>
sudo k3s ctr -n k8s.io images list
kubectl get nodes -L kubernetes.io/hostname
kubectl get runtimeclass nvidia
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu
```

DAG 使用 `image_pull_policy=Never`，预载时必须保留与 `flora_image` 完全相同的 digest 引用。
离线转运也可以使用 containerd OCI archive export/import；导入后仍应核对 digest 引用。
不要将本机 Docker 的 `sha256:736f…` 直接当作 registry manifest digest。

## 触发参数

保留 Kestra 的 `dataset`、`dataset_dir`、`dataset_key`、`episodes`、`include_flags`、
`max_parts`、`inference`、`model_mode`、`segments_execution_id`，默认值也相同。
增加必填 `node_name`（节点 hostname 标签），`flora_image` 改用 repository digest。
`dataset_dir` 支持所选数据类型的相对目录，或表中数据目录内的宿主机绝对路径；不展开 `~`。
Airflow 应保持 `core.dag_run_conf_overrides_params=True`，否则触发参数不会覆盖 DAG Params。

在 Airflow CLI 环境执行，或在 UI Trigger DAG 表单填写：

```bash
airflow dags trigger jiwu_flora --conf '{
  "flora_image": "registry.example.com/robotics/flora@sha256:<manifest-digest>",
  "node_name": "<data-gpu-node-hostname>",
  "dataset": "dagger",
  "dataset_dir": "/home/eisoc/data/debug_datapilot/Robot_data_liqian_20261022_193101",
  "include_flags": true,
  "episodes": [],
  "max_parts": 0,
  "inference": true,
  "model_mode": "tempseg"
}'
```

替换尖括号占位符后运行；`episodes=[]` 表示整包，不连续 episode 也可以指定。
只做 CPU 预检时改为 `inference=false`。Captioner 的 `segments_execution_id` 应填之前日志中
的 `airflow-<摘要>`，也可填同包已有 Kestra execution ID，旧 `tempseg/<id>` 路径仍可回退。

## 输出、重试与清理

Airflow run_id 通常包含冒号；bootstrap 对 `[dag_id, run_id]` 的紧凑 JSON 做 SHA-256，生成
`airflow-<64位摘要>` 作为共享 driver 的 execution ID。两阶段使用相同 ID，日志会打印映射。

```text
<dataset>/temp_seg/
├── results.json
└── runs/airflow-<摘要>/
    ├── validation/
    ├── inference/
    └── artifacts/
        ├── validate/       # manifest.json、TempSeg validation.json
        └── annotate/       # manifest.json、TempSeg results.json 或其他模式 part-*.json
```

这里的 `artifacts` 对应 Kestra 的 outputFiles，但保存在节点数据盘上；Airflow 元数据库不保存
大 JSON，不假装这些路径是已上传的远端对象。下游应按 execution ID 访问持久结果，不能用
根目录“最近成功”文件绑定特定执行。若需要对象存储，应另外配置明确的上传任务。

DAG 无定时调度，`max_active_runs=1`；失败默认不自动重试，避免旧尝试的部分文件被混用。
worker 重启可重新附着现有 Pod。若 Pod 已失败或人为 clear，建议触发一个**新 DAG run**，
获取新输出目录；原生 CLI 的手动 resume 机制仍单独可用。CPU/GPU Pod 最长运行 2/24 小时，
Airflow task 超时为 3/25 小时，Pod 调度超时为 15 分钟。大包应按资源实际情况调整。

成功和失败 Pod 均由 Operator 清理，日志由 Airflow 收集；已写入数据盘的诊断与结果保留。
删除 DAG 或回滚 bundle 不会删除数据目录。回滚时先暂停 DAG，等待或明确终止当前任务，
再恢复上一版 bundle/镜像 digest；通过 GitOps 回滚 RBAC/NetworkPolicy，避免删除整个 namespace。

## 本地验证

在独立 Airflow 环境中从仓库根执行：

```bash
python -m unittest discover -s airflow/tests -v
airflow dags list-import-errors
```

测试检查真实 DAG 导入、参数渲染、Pod 配置、CPU/GPU 顺序、路径约束和 stage driver 交接。
上线验收还需在目标 k3s 上先触发 `inference=false`，再完整运行一包，检查各任务状态、
`complete=true`、逐 episode 覆盖与 flags，并对比独立执行结果。

参考：[Airflow Params](https://airflow.apache.org/docs/apache-airflow/3.1.0/core-concepts/params.html)、
[KubernetesPodOperator](https://airflow.apache.org/docs/apache-airflow-providers-cncf-kubernetes/10.8.1/operators.html)。
