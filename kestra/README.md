# Jiwu Flora Kestra 工作流

[`jiwu_flora.yaml`](jiwu_flora.yaml) 定义 `flora.jiwu / jiwu_flora`。它读取 Jiwu LeRobot 数据集，先校验输入，再按所选模式运行 Flora；默认使用一张 GPU 对 UMI 数据集的全部 episode 运行 TempSeg。执行 ID 由 Kestra 生成，每次执行使用独立输出目录。

## 环境与路径

工作流使用宿主机 Docker 引擎和本地镜像 `jiwu.robotics/robox-datapilot/flora:latest`（`pullPolicy: NEVER`）。Kestra worker 需要访问 Docker socket，Docker Task Runner 需要启用 `volume-enabled`；GPU 推理还需要 NVIDIA 容器运行环境。数据集挂载为可写，以便在数据集内保存结果。镜像和模型缓存应事先准备好；向新磁盘下载权重前须获得用户同意。

| 用途 | 宿主机路径 | 容器路径 |
| --- | --- | --- |
| UMI 数据集父目录 | `/mnt/sdb/jiwu-umi` | `/data/jiwu-umi` |
| DAgger 数据集父目录 | `/mnt/sdb/jiwu-dagger` | `/data/jiwu-dagger` |
| 模型缓存（仅推理任务） | `/mnt/sdb/.datapilot-modelzoo` | `/model_zoo` |

宿主机路径及下方数据集目录名写在 YAML 中；部署到其他环境时需要相应修改。容器以 root 运行，生成文件的属主可能是 root。

## 输入接口

在 Kestra 执行工作流时设置以下输入：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dataset` | SELECT | `umi` | `umi` 或 `dagger`，选择下方对应的数据集根目录。 |
| `max_parts` | INT | `0` | 最多处理的片段数；`0` 表示全部。 |
| `inference` | BOOL | `true` | `true` 先验证再运行 GPU 推理；`false` 仅进行 CPU 输入验证。 |
| `model_mode` | SELECT | `tempseg` | `tempseg` 只做时间分段；`both` 依次运行 TempSeg 和 Captioner；`captioner` 使用已有分段生成描述。仅推理时生效。 |
| `segments_execution_id` | STRING | 空 | `captioner` 模式必填：同一数据集先前成功的 TempSeg 执行 ID，须与所选片段匹配；只允许字母、数字、下划线和连字符。 |

数据集根目录当前固定为：

```text
/mnt/sdb/
├── jiwu-umi/Robot_data_Bing_20261111_144059/          # dataset=umi
│   ├── meta/（info.json、episodes.jsonl 等）
│   └── videos/chunk-*/observation.images.ego_l/
│       └── episode_*.mp4
└── jiwu-dagger/Robot_data_liqian_20261030_174559/     # dataset=dagger
    ├── meta/（info.json、episodes.jsonl 等）
    └── data/chunk-*/
        └── episode_*.parquet
```

UMI 使用原始 `ego_l` 视频和 `human` profile；DAgger 从 Parquet 的 `observation.images.high_cam` 读取 JPEG 帧并使用 `yam` profile，不提供腕部视角。适配器依据元数据寻找 episode，DAgger 会准备不超过 60 秒的 MJPEG AVI 片段；UMI 视频原样传入。输入约束和更详细的适配行为见 [`src/infer/README.md`](../src/infer/README.md)。

## 执行与输出接口

`inference=false` 时运行 `validate`；`inference=true` 时运行 `annotate`，它在模型推理前也会验证输入。输出写在**所选数据集根目录**下，即使模式是 `both` 或 `captioner`，目录名仍为 `tempseg`：

```text
<dataset_root>/
└── tempseg/
    └── <execution-id>/
        ├── manifest.json
        ├── <part-id>.json       # 推理时每个片段一个结果
        └── media/               # DAgger 准备的 AVI；UMI 通常为空
```

- `manifest.json` 记录容器内的 `dataset` 路径、`kind`、`validated`、`inference`、`mode` 和 `parts`。每个 part 包含 ID、视频或源文件路径、帧数、帧率、起始帧、时间偏移、episode 编号和相机信息。路径是容器内路径，宿主机访问时按上表映射。
- `<part-id>.json` 在推理时产生，包含 `segments` 及模型和输入的相关元数据；时间和帧位置已偏移至所属 episode 的坐标。TempSeg 结果包含时间分段；`both` / `captioner` 结果还包含描述和状态。Captioner 片段状态不完整会使执行报错，应检查具体结果和日志。
- 仅验证时不会生成片段推理 JSON。执行失败可能留下部分文件；以 Kestra 执行状态和输出内容共同判断是否完成。原有 `manifest.json` 不会被覆盖。
- `captioner` 模式从 `<dataset_root>/tempseg/<segments_execution_id>/` 读取同名片段结果，并校验来源是否匹配；当前执行的结果写入自己的执行目录。

例如，UMI 执行 `3SAa5VL6qSne7WrH1HfF7l` 的 manifest 位于宿主机：

```text
/mnt/sdb/jiwu-umi/Robot_data_Bing_20261111_144059/tempseg/3SAa5VL6qSne7WrH1HfF7l/manifest.json
```

Kestra 日志记录输入验证、运行进度和结果路径；工作流将已识别的第三方警告和进度转为普通日志，其他标准错误仍显示为 `ERROR`，退出码保持不变。未知的非致命警告仍可能显示为 `ERROR`。
