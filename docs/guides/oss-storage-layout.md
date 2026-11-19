# DataPilot OSS storage layout

Set `DATAPILOT_WORKING_MODE` to `debug` or `release` in the private Compose
configuration shared by Web, indexer, preview, preprocessing and recovery.
Omission selects `debug`.

| Owner | Scope |
| --- | --- |
| Dataset readers and approved workflow publications | `oss://jiwu-datasets/<env>/<dataset-prefix>/` |
| Prepared media and previews | `oss://jiwu-media-buffer/<env>/{indexes,previews,media-cache}/` |
| DataPilot workflow discovery and new revisions | `oss://jiwu-model-zoo/kestra/datapilot/catalog/<env>/` |
| Original YAML backups | `oss://jiwu-model-zoo/kestra/<repo>/<filename>` |
| Archived legacy workflow bytes | `oss://jiwu-model-zoo/kestra/datapilot/legacy/` |
| Model owners | `oss://jiwu-model-zoo/{checkpoints,midtrain}/<project>/` |

Use the native Beijing endpoint `https://oss-cn-beijing.aliyuncs.com` for these
buckets. For a single dataset, register the complete environment and dataset
prefix. For a parent source, register its parent prefix. Use the existing
RustFS mount and credential configuration for RustFS sources.

The workflow catalog reads direct YAML children. Copy a selected source YAML
into the debug catalog, verify its exact SHA-256, and validate it through the
normal DataPilot import and execution flow. Promote the verified bytes to the
release catalog after acceptance. Retain the archived exact revisions and the
original read scope during recovery verification. The default catalog URI
comes from the working mode. Review any `PREPROCESS_WORKFLOW_PREFIX` override
before switching the writer.

UMI publications use the original output paths relative to the captured dataset
root. DataPilot stores its replay packages, per-run manifests, and marker under
`.datapilot/umi/<run-id>/`. A conflicting immutable object blocks the
submission and leaves the prior object available. A version becomes usable
after member and marker verification and SQL acceptance.

## Private service inputs

- `deployment/oss/dataset-reader.env` supplies
  `DATAPILOT_DATASET_OSS_ACCESS_KEY_ID`,
  `DATAPILOT_DATASET_OSS_ACCESS_KEY_SECRET` and the optional
  `DATAPILOT_DATASET_OSS_SECURITY_TOKEN`. Grant list and read only for its
  environment's dataset prefix.
- The separate files `deployment/oss/media-web.env`,
  `deployment/oss/media-indexer.env` and
  `deployment/oss/media-preview.env` supply the matching
  `DATAPILOT_MEDIA_OSS_*` values. Give Web read access and give each producer
  read/write access to its own environment and artifact types. Set
  `DATAPILOT_MEDIA_OSS_ENABLED=1` after those identities are provisioned.
- `deployment/preprocess/oss.env` supplies the workflow catalog identity.
  `deployment/preprocess/umi-oss.env` supplies the original UMI writer identity
  to the restricted finalizer. Scope each to its write prefix and the exact
  retained read/recovery dependencies required by that deployment.
- Keep credentials in owner-only ignored deployment files. Exercise a debug
  sample and confirm the debug writer is denied release writes before enabling
  release. Run the repository's site-release procedure from the integrated
  revision when the release is approved.

The media mirror is derived storage. Keep the original PostgreSQL/Mongo
publication and source evidence and the local hot-cache budgets in place.
