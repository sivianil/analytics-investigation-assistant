"""Run Q&A using an explicitly chosen, trusted model adapter."""
import argparse
import importlib
import json
from pathlib import Path
from sandbox import agent_loop

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question')
    parser.add_argument('--data', default='output/cleaned.jsonl')
    parser.add_argument('--context', default='output/llm_context.json')
    parser.add_argument('--model', required=True, help='Trusted Python module:function returning an action JSON object')
    parser.add_argument('--max-steps', type=int, default=6)
    args = parser.parse_args()
    module, name = args.model.split(':', 1)
    model = getattr(importlib.import_module(module), name)
    context = json.loads(Path(args.context).read_text())
    result = agent_loop(args.question, model, args.data, max_steps=args.max_steps, context=context)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'complete' else 2)
