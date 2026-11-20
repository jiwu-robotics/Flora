# Jiwu Flora Kestra 工作流

[`jiwu_flora.yaml`](jiwu_flora.yaml) 定义 `flora.jiwu / jiwu_flora`。它读取指定目录下的 LeRobot v2.1 数据集，先校验输入，再按所选模式运行 Flora。默认数据类型为 UMI，使用一张 GPU 对所选目录的全部 episode 运行 TempSeg。执行 ID 由 Kestra 生成，每次执行使用独立输出目录。

## 环境与路径

工作流使用宿主机 Docker 引擎，通过必填 `flora_image` 选择已装载、包含当前代码的镜像（`pullPolicy: NEVER`）。必须填写完整 `sha256:<64 位摘要>` 镜像 ID 或 `仓库@sha256:<64 位摘要>`，不能继续使用旧的 `latest`。Kestra worker 需要访问 Docker socket，Docker Task Runner 需要启用 `volume-enabled`；GPU 推理还需要 NVIDIA 容器运行环境。数据集挂载为可写，以便在数据集内保存结果。镜像和模型缓存应事先准备好；向新磁盘下载权重前须获得用户同意。

| 用途 | 宿主机路径 | 容器路径 |
| --- | --- | --- |
| UMI 数据集父目录 | `/mnt/sdb/jiwu-umi` | `/data/jiwu-umi` |
| DAgger 数据集父目录 | `/mnt/sdb/jiwu-dagger` | `/data/jiwu-dagger` |
| 标准数据集父目录 | `/mnt/sdb/datasets` | `/data/datasets` |
| 本机调试数据集父目录 | `/home/eisoc/data/debug_datapilot` | `/data/debug_datapilot` |
| 模型缓存（仅推理任务） | `/mnt/sdb/.datapilot-modelzoo` | `/model_zoo` |

宿主机挂载路径写在 YAML 中；部署到其他环境时需要相应修改。容器以 root 运行，生成文件的属主可能是 root。

## 输入接口

在 Kestra 执行工作流时设置以下输入：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `flora_image` | STRING | 必填 | 包含当前原生汇总代码的本地镜像完整 ID 或仓库 digest。 |
| `dataset_key` | STRING | 空 | TempSeg 数据集标识；空时使用目录名。 |
| `episodes` | ARRAY(INT) | `[]` | TempSeg Episode 编号列表，允许不连续；空列表选择全部，重复或负数拒绝。 |
| `include_flags` | BOOL | `true` | TempSeg 输出 Episode 级切分建议；其他模式不传此参数。 |
| `dataset` | SELECT | `umi` | `umi` 或 `dagger`，选择数据适配器和对应挂载根目录。 |
| `dataset_dir` | STRING | 必填 | 相对于所选类型挂载的路径，或标准数据集挂载及所选类型挂载下的宿主机绝对路径。 |
| `max_parts` | INT | `0` | GPU 推理最多处理的片段数；`0` 表示全部。CPU 预检始终检查完整所选范围。TempSeg 截断结果不能发布。 |
| `inference` | BOOL | `true` | `true` 先验证再运行 GPU 推理；`false` 仅进行 CPU 输入验证。 |
| `model_mode` | SELECT | `tempseg` | `tempseg` 只做时间分段；`both` 依次运行 TempSeg 和 Captioner；`captioner` 使用已有分段生成描述。验证任务同样使用所选模式。 |
| `segments_execution_id` | STRING | 空 | `captioner` 模式必填：同一数据集先前成功的 TempSeg 执行 ID，须与所选片段匹配；只允许字母、数字、下划线和连字符。 |

例如，设置 `dataset=dagger` 和 `dataset_dir=Robot_data_liqian_20261030_174559`
会读取 `/mnt/sdb/jiwu-dagger/Robot_data_liqian_20261030_174559`。
对于标准目录 `/mnt/sdb/datasets/lab_drag_10h/Robot_data_pibiao_20261104_161423/`，
将完整路径填入 `dataset_dir`，并选择 `dataset=dagger` 读取 Parquet 中的 `high_cam`。
也支持 `/home/eisoc/data/debug_datapilot/<包名>` 的绝对路径；`~` 不会自动展开。目录必须存在，并在解析符号链接后仍位于对应挂载根目录下。

```text
/mnt/sdb/
├── jiwu-umi/Robot_data_Bing_20261111_144059/          # dataset=umi, dataset_dir=Robot_data_Bing_20261111_144059
│   ├── meta/（info.json、episodes.jsonl 等）
│   └── videos/chunk-*/observation.images.ego_l/
│       └── episode_*.mp4
└── jiwu-dagger/Robot_data_liqian_20261030_174559/     # dataset=dagger, dataset_dir=Robot_data_liqian_20261030_174559
    ├── meta/（info.json、episodes.jsonl 等）
    └── data/chunk-*/
        └── episode_*.parquet
```

UMI 使用原始 `ego_l` 视频和 `human` profile，每个 episode 最长 90 秒，视频文件最大 708 MiB。DAgger 从 Parquet 的 `observation.images.high_cam` 读取 JPEG 帧并使用 `yam` profile。DAgger 的 `tempseg` 模式直接读取 Parquet，`both` 和 `captioner` 模式使用 MJPEG AVI。DAgger 片段最长 60 秒，JPEG 数据最多 240 MiB。

两种数据集都在后台预取并校验下一个片段，GPU 串行执行，每个阶段复用一个模型会话。`both` 先完成所有片段的 TempSeg，再释放 TempSeg 并加载 Captioner。输入约束见 [Jiwu 数据集适配器指南](../src/infer/README.md)。

## 执行与输出接口

`validate` 每次执行都先运行，完成所有选中 Episode 的独立 CPU 预检。
仅当它成功且 `inference=true` 时才运行 `annotate`。两阶段使用不同目录，避免验证 manifest 与推理输出冲突：

```text
<dataset_root>/temp_seg/
├── results.json                 # 最近一次成功完成的 TempSeg 汇总，原子更新
└── runs/<execution-id>/
    ├── validation/              # 预检 manifest；TempSeg 另有验证态 results.json
    └── inference/
        ├── results.json         # TempSeg 当前执行的原生汇总
        ├── results.identity.json
        ├── manifest.json
        ├── <part-id>.json       # 保留的原生片段证据
        ├── media/
        └── segments/            # both 模式的中间分段结果
```

TempSeg 必须 `complete=true`，且 selection、producer、源摘要与预检一致，每个 Episode
状态为 success 且覆盖全部帧，才会更新根目录的 `results.json` 并交接给 Kestra。
`max_parts` 截断、验证态输出和失败不会覆盖上次成功结果；诊断文件保留在本次执行目录。
根目录文件是最近完成执行的便捷副本；并发执行以最后成功发布者为准，审计和下游绑定应使用
各自执行目录的文件。`part_id` 对应本次 `inference/` 中的原生片段文件。

Kestra 验证任务捕获 `manifest.json` 和 `validation.json`；TempSeg 推理捕获
`manifest.json` 和 `results.json`。其他模型模式保留片段输出交接，内部 identity 文件不会上传。

- `manifest.json` 记录容器内的 `dataset` 路径、`kind`、`validated`、`inference`、`mode` 和 `parts`。每个 part 包含 ID、视频或源文件路径、帧数、帧率、起始帧、时间偏移、episode 编号和相机信息。路径是容器内路径，宿主机访问时按上表映射。
- `<part-id>.json` 在推理时产生，包含 `segments` 及模型和输入的相关元数据；时间和帧位置已偏移至所属 episode 的坐标。TempSeg 结果包含时间分段；`both` / `captioner` 结果还包含描述和状态。Captioner 片段状态不完整会使执行报错，应检查具体结果和日志。
- 仅验证时不会生成片段推理 JSON。执行失败可能留下部分文件；以 Kestra 执行状态和输出内容共同判断是否完成。原有 `manifest.json` 不会被覆盖。
- `captioner` 优先从 `<dataset_root>/temp_seg/runs/<segments_execution_id>/inference/` 读取同名片段结果；兼容回退到旧的 `tempseg/<segments_execution_id>/`，并校验来源是否匹配。

例如，UMI 执行 `3SAa5VL6qSne7WrH1HfF7l` 的 manifest 位于宿主机：

```text
/mnt/sdb/jiwu-umi/Robot_data_Bing_20261111_144059/temp_seg/runs/3SAa5VL6qSne7WrH1HfF7l/inference/manifest.json
```

Kestra 日志记录输入验证、运行进度和结果路径；工作流将已识别的第三方警告和进度转为普通日志，其他标准错误仍显示为 `ERROR`，退出码保持不变。未知的非致命警告仍可能显示为 `ERROR`。

长任务可通过容器内 `python -m src.infer --kind dagger --mode tempseg --direct-parquet --run --resume --output <同一输出目录> --dataset <数据集目录>` 续跑。续跑检查源文件、片段、代码、模型版本和参数；不支持使用自定义合并权重续跑。已完成片段单独原子写入，manifest 在整次运行完成后写入。日志的 `episode_hash`、`part_prefetched`、`window_preparation` 和 `input_preparation` 分别记录文件哈希、预取、窗口准备及主机侧传输耗时；`part_resources` 包含推理耗时、GPU 峰值和进程峰值内存；峰值需要结合其他进程和容器限制评估。

## 镜像准备与离线运行

镜像须包含当前 `src/infer`，单纯从其他机器导入旧镜像不等于更新代码。可在 Docker 引擎所在主机执行：

```bash
docker build -f docker/Dockerfile.ubuntu24.04-2.11.0+cu128 -t flora:native-results-v1 .
docker image inspect flora:native-results-v1 --format '{{.Id}}'
```

将输出的完整镜像 ID 填入 `flora_image`。工作流启动时也会检查 CLI 是否支持
`--dataset-key` 和 `--episodes`，缺少时在 GPU 推理前失败。
容器禁用网络并设置 Hugging Face 离线模式；基座、adapter 或 Captioner 所需权重应已存在。
模型缓存挂载保留可写，以允许 Hugging Face 创建锁文件；离线运行不会下载新权重。

本次配置修改只更新仓库文件，不会自动构建镜像、部署工作流或启动推理。
