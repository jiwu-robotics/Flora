"""Run only the temporal segmentation stage of the annotation pipeline."""
import json
import math
import sys
import time

from batch_utils.api import DataEnginePipeline
from batch_utils.cli import jobs, parser
from batch_utils.config import MODELS, PROFILE_POOLS


def main(argv=None):
    p = parser()
    p.description = 'FLORA TempSeg: timestamped action intervals without captions.'
    args = p.parse_args(argv)
    try:
        items = jobs(args, p)
        if not args.validate_only and not args.overwrite:
            for _, output in items:
                if output.exists():
                    raise FileExistsError(f'Output already exists: {output}. Use --overwrite to replace it.')
        for kwargs, output in items:
            if args.validate_only:
                inspection = DataEnginePipeline().inspect_inputs(**kwargs)
                inspection['model_revisions'] = {key: MODELS[key] for key in ('tempseg', 'tempseg_base')}
                print(json.dumps(inspection, allow_nan=False))
                continue
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError('CUDA is required for inference. Use --validate-only to check inputs on CPU.')
            from batch_utils.models import Session, runtime_event
            from batch_utils.pipeline import segment

            videos, profile = DataEnginePipeline._inputs(
                kwargs['video'], kwargs.get('profile', 'human'), kwargs.get('left_wrist'),
                kwargs.get('right_wrist'), kwargs.get('yam32', False), kwargs.get('instruction', ''))
            pool = 'yam32' if kwargs.get('yam32', False) else PROFILE_POOLS[profile]
            session = Session()
            started = time.monotonic()
            try:
                segments, audit = segment(videos, pool, session, kwargs.get('instruction', ''),
                                          lambda fraction, desc='': print(f'{fraction:.0%} {desc}', file=sys.stderr, flush=True))
            finally:
                session.close()
            rows = []
            for item in segments:
                start, end = item['start_s'], item['end_s']
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= videos['main'].duration_s + 0.001):
                    raise RuntimeError('The pipeline returned an invalid segment interval.')
                rows.append(dict(start_s=start, end_s=end, segmentation_provenance=item['metadata'].get('segmentation_provenance', 'fine')))
            runtime_event('segmentation_complete', windows=len(audit), segments=len(rows))
            result = dict(schema_version='flora_tempseg_v1', duration_s=videos['main'].duration_s,
                          segments=rows, elapsed_s=round(time.monotonic() - started, 2),
                          source_clock='seconds relative to the first native source presentation timestamp',
                          profile=profile, camera_roles=list(videos),
                          model_revisions={key: MODELS[key] for key in ('tempseg', 'tempseg_base')},
                          input_sha256={role: video.sha256 for role, video in videos.items()})
            if args.include_audit:
                result['temporal_windows'] = audit
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('w' if args.overwrite else 'x') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write('\n')
            print(json.dumps({'output': str(output), 'segments': len(rows)}))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f'FLORA inference failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
