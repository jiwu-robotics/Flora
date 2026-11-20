# Flora 原生 results.json 与 DataPilot 对接改造指南

本文定义输出协议和迁移步骤。Flora 侧已接入原生汇总器与 CLI，使用说明见
`src/infer/README.md`，结构契约见 `src/infer/results.schema.json`；DataPilot 与通用 runner
部分仍待平台实现和联调。原始方案基于 Flora
`786545f` 与 DataPilot 当前实现检查编写。此次目标是让 Flora 独立完成算法结果整理，
由通用 runner 承担执行管理，最终移除 DataPilot 的 Flora 专用 bridge。

## 1. 改造范围与职责

```text
Kestra
  └─ 通用 worker runner
       └─ python -m src.infer ... --mode tempseg --run
            └─ <output>/results.json
                 └─ DataPilot 校验、私有保存、人工确认与建议发布
```

| 所有者 | 职责 |
| --- | --- |
| Flora | 输入读取与验证、模型推理、分块结果汇总、原始帧映射、来源摘要、原子写入 results.json |
| 通用 runner | GPU 准入、租约心跳、子进程生命周期、取消、输出大小限制、文件 SHA-256 与交接 |
| Kestra | 任务编排、容器启动、调度状态、超时/取消传递、输出文件捕获 |
| DataPilot | 当前执行权限、来源与协议校验、证据保存、人工确认、建议展示 |

Flora 不调用 DataPilot 私有接口，不获取数据库凭据，不申请平台 GPU 租约，不生成平台
run_id、node_attempt 或 publication_id。通用 runner 不解析算法 segments，不转换帧号，
不改变模型输出。平台执行信息与文件摘要保存在 runner 的交接记录中，与算法 JSON 分开。

本次首先覆盖 `--mode tempseg` 的 DAgger 和 UMI；不改变 Captioner、Rewarder 的算法行为，
不调整提示词、采样、模型配置或固定模型版本。现有 per-part 输出、manifest 和 Captioner
复用路径保留，统一文件是新增的消费接口。

## 2. 现有能力和修改入口

| 文件 | 当前行为 | 建议修改 |
| --- | --- | --- |
| `src/infer/__main__.py` | CLI、视频准备、分阶段运行；`write_episode_result()` 恢复 Episode 时间/帧偏移 | 在 TempSeg 完成后调用共同汇总器；验证模式也生成明确标识的检查结果 |
| `src/infer/direct.py` | DAgger 原生 Parquet 分块、时间转帧、resume、原子写入 per-part JSON | 将已验证 part 提交给共同汇总器；resume 后重新生成整体结果 |
| `captioner/batch_utils/segment_output.py` | `frame_span()` 和 `boundary_flags()` | 复用规则，补充协议标识与测试；不要复制一套近似实现 |
| 新增 `src/infer/results.py` | 共享汇总入口 | 一个聚合生命周期对象持有输入清单、完成 part 和覆盖范围；纯校验/坐标函数保持独立 |
| `src/infer/README.md` | 当前参数和输出说明 | 记录新协议、结果位置、坐标与失败语义 |
| `tests/test_infer_output.py`、`tests/test_parquet_tempseg.py` | 输出及直接 Parquet 验证 | 增加下面的契约测试 |

当前两条输入路径均主要输出 per-part JSON 和 `manifest.json`，不能把这些文件简单拼接
就视为完整结果。尤其需要明确源文件身份、预期 Episode 清单和完整处理范围。

## 3. 建议协议 flora_results_v1

保留旧格式的 `dataset → chunk → episode` 结构，放进 `results`。旧消费者需改为读取
`document.results`，因此这不是对旧文件的无条件向后兼容扩展。

以下展示成功处理一个 600 帧 Episode 的结构；尖括号值是占位值，实际摘要必须为完整
SHA-256。这个例子只展示一个检测区间：处理完整不等于检测区间覆盖全部输入。

```json
{
  "schema_version": "flora_results_v1",
  "producer": {
    "name": "flora",
    "revision": "<flora-code-revision>",
    "models": {
      "tempseg": {"revision": "<revision>", "sha256": "<sha256>"},
      "tempseg_base": {"revision": "<revision>"}
    }
  },
  "mode": "tempseg",
  "parameters": {
    "episode_index": 0,
    "max_parts": 0,
    "inference": true,
    "direct_parquet": true,
    "image_key": "observation.images.high_cam",
    "include_flags": true,
    "flag_merge_gap": 30,
    "instruction": ""
  },
  "selection": {
    "dataset_key": "dataset-id",
    "episodes": [{"chunk": "chunk-000", "episode_index": 0}]
  },
  "coordinates": {
    "frames": "original_episode_row_index",
    "interval": "half_open",
    "seconds": "relative_to_first_source_presentation_timestamp",
    "frame_mapping": "flora_frame_span_v1"
  },
  "flags_policy": "episode_boundaries_v1",
  "complete": true,
  "results": {
    "dataset-id": {
      "chunk-000": {
        "0": {
          "parquet_name": "data/chunk-000/episode_000000.parquet",
          "frame_count": 600,
          "source": {
            "kind": "dagger",
            "input_type": "parquet",
            "camera_key": "observation.images.high_cam",
            "files": [
              {"path": "meta/info.json", "sha256": "<sha256>"},
              {"path": "meta/episodes.jsonl", "sha256": "<sha256>"},
              {"path": "data/chunk-000/episode_000000.parquet", "sha256": "<sha256>"}
            ]
          },
          "status": "success",
          "processed_ranges": [{"start_frame": 0, "end_frame": 600}],
          "segments": [
            {
              "start_frame": 0,
              "end_frame": 285,
              "start_s": 0.0,
              "end_s": 9.5,
              "part_id": "episode_000000_part_000",
              "segmentation_provenance": "fine"
            }
          ],
          "flags": [285]
        }
      }
    }
  }
}
```

### 身份、来源和执行参数

- 第一版限定一次执行一个数据集。`dataset_key` 是调用方传入的原样回显标识，建议增加
  `--dataset-key`；独立运行可默认使用目录名。它不是权限凭据，也不能单独证明数据身份。
- `selection.episodes` 在处理前确定，必须列出此次选择的所有 Episode。`--max-parts`
  限制计算量，不得通过缩短预期清单伪造完整结果。数据集内 chunk/episode 路径由真实元数据
  解析，不能固定假设每个 chunk 的大小。
- `source.files` 覆盖实际读取的数据与解释所需元数据。UMI 包含原生视频、Parquet 和
  时间映射依赖；摘要必须对应实际使用的字节。派生 AVI 或分块 JPEG 摘要不能替代原文件摘要。
- 路径相对数据集根目录，禁止绝对路径、`..` 和逃逸根目录的符号链接。不要输出平台挂载路径。
- 对可变输入，在完成前复核来源未变化；发现变化则失败。大文件采用流式摘要，避免整文件入内存。
- `producer.models` 保留真实模型身份；自定义 merged weights 需要内容摘要及实际可获得的
  来源信息，不能冒充默认模型。DataPilot 是否批准该模型由平台决定。
- `parameters` 记录生效参数而非仅记录显式 CLI 参数；继续保留原生的 profile、模型 provenance
  等验证信息。无法确定必要来源或模型身份时，不得输出可发布成功结果。

### 坐标与分块合并

- 帧号是原 Episode 零基行序号，不是模型采样帧号或 part 内序号。
- 区间统一为 `[start_frame, end_frame)`，满足 `0 <= start_frame < end_frame <= frame_count`。
- 秒坐标按原始呈现时间轴归一化；不要把带间断的采集时钟和呈现时间轴混用。
- 汇总器接收已经恢复 Episode 偏移的结果，不能再次加偏移。原生 part 若仍使用局部坐标，
  应在唯一明确的入口转换一次，并检查其 part 身份和覆盖范围。
- UMI 必须验证视频 PTS 与原始行的对应关系；无法证明映射时失败，不能退化为 `seconds * fps`。
- 保留并稳定排序所有原生 segment；允许并发动作区间重叠，不自动合并相邻动作或补齐空白。
  `part_id` 关联保留的原生 part 证据；续跑不得重复追加同一个 part。

**已发现的兼容差异：** Flora 当前 `frame_span()` 对开始时间取覆盖该时间的前一帧
（`bisect_right - 1`），结束取 `bisect_left`，并保证至少一帧；DataPilot 当前
`flora_results.py` 对起止都使用 `bisect_left`。不能声称迁移前后帧区间天然一致。
新协议建议用 `flora_frame_span_v1` 明确采用 Flora 当前规则，先拒绝越界/非有限时间，
再做映射。DataPilot 新校验器同步识别该规则，旧证据继续沿用旧规则。需用非整帧时刻、
可变帧率和短区间样例记录差异，不允许悄悄重写历史结果。

### flags 规则

`segments` 是主要结果，`flags` 是可选的切分建议，不能反过来改变 segments。
`include_flags=false` 时省略 flags，而不是用空列表表示未计算。

建议 `episode_boundaries_v1` 复用当前 `boundary_flags()`：

1. 从整个 Episode 的 segments 提取去重后的起止帧。
2. 仅保留 `10 <= boundary < frame_count - 10`。
3. 相邻间距严格小于 `flag_merge_gap` 的边界归为一组；0 表示不合并。
4. 对各组均值按现有整数公式四舍五入，输出升序列表。

必须在 Episode 汇总后计算，不能直接拼接 per-part flags。当前直接 Parquet 路径是在
part 内筛选/合并再加偏移，分块边缘和跨块近邻会产生不同结果。保留旧 per-part 文件语义，
为新汇总文件明确声明新策略，并加入跨块测试。

### 完整性和失败

- 每个选中 Episode 必须有一条结果，状态限定为 `success`、`partial`、`failed`、
  `not_processed`、`validated`。失败记录增加 `error: {code, message}`，不要泄露凭据或私有路径。
- `processed_ranges` 仅记录成功执行模型的原始帧范围，升序、无重叠，可合并相邻范围；
  不可从 segments 推导。合法的 `segments: []` 仍可能表示完整推理成功。
- `success` 要求完整覆盖该 Episode；`partial` 表示成功处理了部分范围；验证模式使用
  `validated`，segments 为空、processed_ranges 为空、inference 为 false。
- `complete=true` 当且仅当 selection 中所有 Episode 都成功推理且完整覆盖；不能仅依赖
  manifest 声明或进程退出码。验证模式、失败、未处理和部分结果均为 false。
- `max_parts` 有界执行可正常退出，但结果必须如实标记 partial/complete。DataPilot 只有在
  所选输入完整、模型获准、来源匹配时才允许确认发布；不要求覆盖整个数据集。
- 异常执行退出非零；若能可靠形成诊断结果，可以原子写入 complete=false 的文件。取消或
  强制终止不保证生成文件，平台不得把此前遗留文件当成本次成功产物。

## 4. 文件写入与 CLI 行为

统一文件固定为 `<output>/results.json`。保留现有 `--output` 目录参数，不需要增加一个
Flora 专用后处理命令。增加 `--dataset-key` 后，可按以下预期接口运行：

```bash
# CPU validation; --dataset-key is supported by src.infer.
python -m src.infer --kind dagger --mode tempseg \
  --dataset /data/example --dataset-key example \
  --direct-parquet --episode 0 --output /outputs/run-001

# Run only after input validation, with approved GPU/model resources.
python -m src.infer --kind dagger --mode tempseg \
  --dataset /data/example --dataset-key example \
  --direct-parquet --episode 0 --include-flags --run --output /outputs/run-002
```

- 未指定 `--output` 时，保留当前 Flora 的默认输出规则；DataPilot 接入必须显式传入独立
  可写输出目录，并将源数据集只读挂载。是否在数据集旁保存结果是调用方的目录选择。
- 使用同目录临时文件、严格 JSON 编码、flush/fsync 和原子 rename 完成发布。
  不允许 NaN/Infinity，不允许 reader 读到半个文件；沿用明确的覆盖/resume 策略。
- 每个执行 attempt 使用独立目录。resume 必须核对来源、代码、模型和全部有效参数，
  从匹配的已完成 part 重建汇总，不能盲目沿用旧 results.json。
- 进程退出前完成所有写入，之后不再修改。runner 只交接固定目标文件，不扫描任意路径。
- 保留现有日志协议，可增加最终 `{"results": ".../results.json", "complete": true}`
  定位信息；stdout 日志不能替代文件内容。
- 汇总 JSON 不携带视频、全量时间戳数组或 base64 数据。当前 DataPilot worker 结果有
  8 MiB 限制，首版接入必须核算限制；超限明确失败，不截断。需要大结果时再单独设计分片协议。

## 5. DataPilot 配套修改（不由 Flora 承担）

不能仅删 `flora_bridge.py` 或改文件名就完成接入，必须同步完成以下工作：

1. 从现有 `worker_runtime.py` 提取通用运行入口，承接 GPU 申请、租约续期、取消和进程组
   清理；租约失效时停止子进程，失去权限的旧 attempt 不能继续交接结果。
2. runner 成功等待算法退出后，检查固定输出是合规的普通文件，计算字节数和 SHA-256，
   将执行身份、attempt/fence、文件摘要交给服务端；算法 JSON 无需包含这些平台字段。
3. 更新工作流资格校验、命令模板、运行时代码摘要、挂载和 Kestra 输出声明。当前
   `result.json` 是带平台 envelope 的文件，新 `results.json` 是算法结果，二者不能直接互换。
4. 新增 `flora_results_v1` 接收/校验器：校验 selection、来源摘要、批准模型、帧映射规则、
   coverage 和 segments；服务端再次核对收到文件的摘要与当前 attempt 权限。
5. 将已验证结果投影为现有建议/证据结构，继续显式确认后发布，不自动写项目标签或切分点。
6. 保留既有 `flora_annotation_v1` 历史读取能力。新旧工作流绑定应使用可区分的版本，
   不覆盖旧运行的协议身份。待新链路验证通过后再移除专用 bridge 的新执行引用。

Flora 原生汇总器上线与 DataPilot 完整移除 bridge 是两个交付点。通用 runner 尚未落地前，
不要取消现有执行管理；过渡适配如有必要，仅放在平台侧并明确退役条件。

## 6. 实施顺序与验收

1. 先建立 `flora_results_v1` schema/fixtures，冻结坐标、flags 和完整性规则。
2. 实现共享汇总器，首先接入 direct Parquet，再接入视频路径与 UMI。
3. 补齐源文件摘要、参数/模型身份、输入选择清单、原子写入和 resume 行为。
4. 更新 README 和 CLI 帮助；保留既有 per-part 文件供 Captioner 和诊断使用。
5. 配合 DataPilot 新接收器做协议对接，再完成通用 runner 切换。

至少覆盖以下验证：

- DAgger 单 part、多 part、多 Episode，以及 UMI 非恒定 PTS 的原始行映射。
- 非整帧起点、末帧边界、短区间、重叠动作、空检测结果和越界/非有限时间。
- 跨 part 偏移仅加一次；flags 跨 part 聚合和首尾过滤符合声明的策略。
- `max_parts` 截断、验证模式、某 Episode 失败、未处理 Episode 均不能伪装 complete。
- 原文件变化、缺失/重复 part、来源摘要不匹配、模型或参数变化时拒绝旧 resume 产物。
- 写入中断不会暴露半文件；重复运行不会意外覆盖；相同输入确定性汇总不重复 segment。
- 原有 Captioner 对 per-part TempSeg 输出的读取不受影响。
- DataPilot 联调：错误来源/模型/执行身份被拒绝，完整结果确认后可见，历史结果仍可读取。
- runner 联调：取消与租约失效停止进程，摘要不匹配或过期 attempt 无法交接。

先使用小型 fixtures 和 CPU 验证测试，不为协议开发下载新权重或启动大规模 GPU 作业。
需要真实推理时遵守仓库既有资源审批与模型固定版本规则。
