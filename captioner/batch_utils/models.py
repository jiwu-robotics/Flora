from collections import Counter
from pathlib import Path
import gc
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from .config import MODELS, MODEL_CACHE
_LOCK = threading.Lock()
_MANIFEST_LOCK = threading.Lock()
_VERIFIED_MANIFESTS = {}

class NotReady(RuntimeError):
    pass

def verify_cuda_residency(model):
    devices = Counter((str(p.device) for p in model.parameters()))
    if not devices or any((not d.startswith('cuda:') for d in devices)):
        raise NotReady('GPU memory is insufficient for this native Captioner configuration.')
    return dict(devices)

def runtime_event(event, **values):
    print('FLORA_RUNTIME ' + json.dumps(dict(event=event, utc=datetime.now(timezone.utc).isoformat(), **values), sort_keys=True), flush=True)

def ready():
    if os.environ.get('FLORA_ENABLE_INFERENCE', '0') != '1':
        return (False, 'Preview ready · live annotation is paused.')
    import torch
    if not torch.cuda.is_available():
        return (False, 'Preview ready · GPU hardware is needed for annotation.')
    if sum((torch.cuda.get_device_properties(i).total_memory for i in range(torch.cuda.device_count()))) < 75 * 1024 ** 3:
        return (False, 'Annotation needs an 80 GB GPU or a validated multi-GPU configuration.')
    if not os.environ.get('HF_TOKEN'):
        return (False, 'Annotation is waiting for access to the private weights.')
    return (True, 'Ready to annotate · one video at a time.')

def snapshot(kind):
    from huggingface_hub import snapshot_download
    spec = dict(MODELS[kind])
    spec['repo'] = os.environ.get(spec.get('repo_env', ''), spec['repo'])
    if not spec['repo']:
        raise ValueError('Set ' + spec['repo_env'] + ' to the released checkpoint repository.')
    patterns = ['adapter_config.json', 'adapter_model.safetensors', 'config.json', 'generation_config.json', 'model.safetensors.index.json', 'model-*.safetensors', 'processor_config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja', 'README.md', 'MODEL_PROVENANCE.json', 'SOURCE_MANIFEST.sha256']
    return Path(snapshot_download(spec['repo'], revision=spec['revision'], token=os.environ.get('HF_TOKEN'), allow_patterns=patterns, local_dir=MODEL_CACHE / kind))

def load_merged_tempseg(path, torch):
    from transformers import AutoModelForImageTextToText
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5PreTrainedModel
    from production_gdn_fix import _keep_native_gdn_fp32
    from verify_gdn import verify
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_dir() or not (path / 'MERGE_PROVENANCE.json').is_file():
        raise ValueError('weights_path must be a merged Flora TempSeg checkpoint directory')
    provenance = json.loads((path / 'MERGE_PROVENANCE.json').read_text())
    if provenance.get('schema') != 'flora_tempseg_merged_checkpoint_v1' or not provenance.get('adapter_merged'):
        raise ValueError('The selected directory is not a merged Flora TempSeg checkpoint')
    if provenance.get('base_revision') != MODELS['tempseg_base']['revision'] or provenance.get('adapter_sha256') != MODELS['tempseg']['sha256']:
        raise ValueError('The merged checkpoint does not match the pinned Flora TempSeg weights')
    _keep_native_gdn_fp32(Qwen3_5PreTrainedModel)
    model, info = AutoModelForImageTextToText.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16, attn_implementation='sdpa', output_loading_info=True)
    if any((info.get(k) for k in ['missing_keys', 'mismatched_keys', 'error_msgs', 'unexpected_keys'])):
        raise RuntimeError('The merged TempSeg checkpoint did not load completely')
    model.to('cuda:0').eval()
    devices = verify_cuda_residency(model)
    gdn = verify(model, path)
    original_generate = model.generate

    def generate_bf16(self, *args, **kwargs):
        with torch.autocast(device_type='cuda', dtype=torch.bfloat16):
            return original_generate(*args, **kwargs)

    import types
    model.generate = types.MethodType(generate_bf16, model)
    return model, {'merged': True, 'provenance': provenance, 'gdn': gdn, 'loading_info': info, 'parameter_devices': devices, 'parameter_dtypes': dict(Counter((str(p.dtype) for p in model.parameters())))}

def processor(kind, path):
    from transformers import AutoProcessor
    from transformers.models.qwen3_vl.video_processing_qwen3_vl import Qwen3VLVideoProcessor
    proc = AutoProcessor.from_pretrained(path, local_files_only=True, use_fast=True, min_pixels=1024, max_pixels=589824, video_processor=Qwen3VLVideoProcessor.from_pretrained(path, local_files_only=True, fps=4 if kind == 'tempseg' else 8, max_frames=128 if kind == 'tempseg' else 40))
    proc.chat_template = (path / 'chat_template.jinja').read_text()
    return proc

def validate_manifest(path):
    with _MANIFEST_LOCK:
        _validate_manifest(path)

def _validate_manifest(path):
    started = time.monotonic()
    allowed_root = path.parent.parent if path.parent.name == 'snapshots' else path
    manifest = (path / 'SOURCE_MANIFEST.sha256').read_bytes()
    key = str(path.resolve())
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    files = []

    def fingerprint(source):
        resolved = source.resolve()
        if not resolved.is_relative_to(allowed_root.resolve()):
            raise RuntimeError('Invalid model manifest')
        stat = resolved.stat()
        return (str(resolved), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    for line in manifest.decode().splitlines():
        if not line.strip():
            continue
        expected, filename = line.split(maxsplit=1)
        relative = Path(filename.lstrip('*'))
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid model manifest')
        source = path / relative
        if not source.resolve().is_relative_to(allowed_root.resolve()):
            runtime_event('manifest_path_rejected', file=filename, snapshot=str(path), target=str(source.resolve()), allowed_root=str(allowed_root.resolve()))
            raise RuntimeError('Invalid model manifest')
        files.append((source, expected, fingerprint(source)))
    before = tuple(((str(source), expected, stamp) for source, expected, stamp in files))
    if _VERIFIED_MANIFESTS.get(key) == (manifest_sha, before):
        runtime_event('manifest_verified_reuse', kind=path.name, files=len(files), payload_bytes_read=0, elapsed_s=round(time.monotonic() - started, 3))
        return
    _VERIFIED_MANIFESTS.pop(key, None)
    for source, expected, _ in files:
        with source.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != expected:
                raise RuntimeError('A model asset failed its integrity check')
    after = tuple(((str(source), expected, fingerprint(source)) for source, expected, _ in files))
    if before != after or manifest != (path / 'SOURCE_MANIFEST.sha256').read_bytes():
        raise RuntimeError('A model asset changed during its integrity check')
    _VERIFIED_MANIFESTS[key] = (manifest_sha, after)
    runtime_event('manifest_full_verification', kind=path.name, files=len(files), payload_bytes_read=sum((stamp[3] for _, _, stamp in files)), elapsed_s=round(time.monotonic() - started, 3))

def preflight_adapter_download():
    path = snapshot('tempseg')
    validate_manifest(path)
    runtime_event('adapter_download_preflight_pass', revision=MODELS['tempseg']['revision'], adapter_sha256=MODELS['tempseg']['sha256'], directory=str(path))

class Session:

    def __init__(self, tempseg_weights_path=None):
        self.model = self.proc = None
        self.audit = {}
        self.tempseg_weights_path = tempseg_weights_path
        self.kind = None

    def load(self, kind):
        if self.kind == kind and self.model is not None and self.proc is not None:
            return self.model, self.proc
        import torch
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(4)
        load_started = time.monotonic()
        from transformers import AutoModelForImageTextToText
        from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5PreTrainedModel
        from production_gdn_fix import _keep_native_gdn_fp32
        from verify_gdn import verify
        self.close()
        runtime_event('model_load_start', kind=kind, cpu_threads=torch.get_num_threads(), previous_cpu_threads=previous_threads)
        _keep_native_gdn_fp32(Qwen3_5PreTrainedModel)
        merged = Path(self.tempseg_weights_path).expanduser().resolve(strict=True) if kind == 'tempseg' and self.tempseg_weights_path else None
        path = merged or snapshot(kind)
        runtime_event('model_assets_ready', kind=kind, elapsed_s=round(time.monotonic() - load_started, 3))
        if merged:
            self.model, self.audit[kind] = load_merged_tempseg(path, torch)
            runtime_event('merged_checkpoint_verified', kind=kind, directory=str(path), adapter_sha256=self.audit[kind]['provenance']['adapter_sha256'])
        else:
            validate_manifest(path)
            runtime_event('model_assets_verified', kind=kind, elapsed_s=round(time.monotonic() - load_started, 3))
        if kind == 'tempseg' and not merged:
            base_spec = MODELS['tempseg_base']
            from huggingface_hub import snapshot_download
            base = snapshot_download(base_spec['repo'], revision=base_spec['revision'], token=os.environ.get('HF_TOKEN'), allow_patterns=['*.safetensors', '*.json', '*.jinja'])
            from tempseg_fp32_loader import load
            records = {}
            self.model = load({'base': base, 'export': str(path), 'adapter_sha256': MODELS[kind]['sha256']}, lambda name, value: records.__setitem__(name, value))
            self.audit[kind] = records
        elif kind != 'tempseg':
            index = json.loads((path / 'model.safetensors.index.json').read_text())
            extra = {k for k in index['weight_map'] if '_extra_state' in k}
            memory = {i: f'{max(1, int(torch.cuda.get_device_properties(i).total_memory / 1024 ** 3) - 12)}GiB' for i in range(torch.cuda.device_count())}
            self.model, info = AutoModelForImageTextToText.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16, attn_implementation={'text_config': 'sdpa', 'vision_config': 'sdpa'}, device_map='balanced', max_memory=memory, output_loading_info=True)
            if any((info.get(k) for k in ['missing_keys', 'mismatched_keys', 'error_msgs'])) or not set(info.get('unexpected_keys', [])) <= extra:
                raise RuntimeError('The released Captioner did not load completely')
            devices = verify_cuda_residency(self.model)
            self.model.eval()
            self.audit[kind] = {'gdn': verify(self.model, path), 'loading_info': info, 'parameter_devices': devices, 'parameter_dtypes': dict(Counter((str(p.dtype) for p in self.model.parameters())))}
        runtime_event('model_parameters_verified', kind=kind, elapsed_s=round(time.monotonic() - load_started, 3))
        self.proc = processor(kind, path)
        if kind == 'tempseg':
            if self.audit[kind].get('merged'):
                gdn = self.audit[kind]['gdn']
                verification = dict(merged_checkpoint=True, gdn_values_exact=gdn['all_values_equal_saved_checkpoint'], gdn_fp32=gdn['all_runtime_fp32'], parameter_dtypes=self.audit[kind]['parameter_dtypes'])
            else:
                adapter = self.audit[kind]['ADAPTER_VALUE_VERIFICATION.json']
                gdn = self.audit[kind]['GDN_VALUE_VERIFICATION.json']
                verification = dict(adapter_tensors=adapter['tensors'], adapter_values_exact=adapter['all_saved_values_exact_before_and_after_placement'], adapter_fp32=adapter['holders_fp32_before_assignment'], gdn_values_exact=gdn['all_values_equal_saved_checkpoint'], gdn_fp32=gdn['all_runtime_fp32'])
        else:
            gdn = self.audit[kind]['gdn']
            verification = dict(gdn_values_exact=gdn['all_values_equal_saved_checkpoint'], gdn_fp32=gdn['all_runtime_fp32'], parameter_dtypes=self.audit[kind]['parameter_dtypes'])
        runtime_event('model_ready', kind=kind, revision=MODELS[kind]['revision'], torch_version=torch.__version__, gpu=torch.cuda.get_device_name(0), allocated_gib=round(torch.cuda.memory_allocated() / 1024 ** 3, 3), **verification)
        self.kind = kind
        return (self.model, self.proc)

    def close(self):
        self.kind = None
        self.model = self.proc = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def generate(model, proc, inputs, budget):
    import torch
    inputs = dict(inputs)
    inputs.pop('video_metadata', None)
    n = inputs['input_ids'].shape[1]
    if n + budget > 32768:
        raise InputErrorForModel('The selected video exceeds the native model context budget.')
    input_tensors = {k: {'dtype': str(v.dtype), 'shape': list(v.shape), 'sha256': hashlib.sha256(v.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()} for k, v in inputs.items() if torch.is_tensor(v)}
    input_tensor_digest = hashlib.sha256(json.dumps(input_tensors, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    device = next(model.parameters()).device
    args = {k: v.to(device) if torch.is_tensor(v) else v for k, v in inputs.items()}
    eos = proc.tokenizer.eos_token_id
    started = time.monotonic()
    runtime_event('generation_start', input_tokens=n, output_limit=budget, input_tensor_digest=input_tensor_digest, input_tensors=input_tensors)
    with torch.inference_mode():
        output = model.generate(**args, do_sample=False, num_beams=1, max_new_tokens=budget, eos_token_id=eos, pad_token_id=proc.tokenizer.pad_token_id, use_cache=True, max_time=300)
    ids = output[0, n:].cpu().tolist()
    stop = bool(ids) and ids[-1] in ([eos] if isinstance(eos, int) else eos)
    text = proc.tokenizer.decode(ids, skip_special_tokens=True).strip()
    runtime_event('generation_end', input_tokens=n, output_limit=budget, generated_tokens=len(ids), complete=stop and bool(text), elapsed_s=round(time.monotonic() - started, 3), peak_allocated_gib=round(torch.cuda.max_memory_allocated() / 1024 ** 3, 3))
    if not stop or not text:
        raise InputErrorForModel('The model did not return a complete output for this input.')
    return text

class InputErrorForModel(RuntimeError):
    pass
