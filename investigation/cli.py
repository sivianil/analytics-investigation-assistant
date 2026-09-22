import argparse
import json

from investigation.config import Settings
from investigation.engine import Investigator
from investigation.model import Embeddings
from investigation.retrieval import ContextStore


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('index', help='Build the versioned Qdrant context index')
    ask = commands.add_parser('ask', help='Run a bounded investigation')
    ask.add_argument('question')
    commands.add_parser('serve', help='Serve the authenticated API on 127.0.0.1:8000')
    args = parser.parse_args()
    settings = Settings()
    if args.command == 'serve':
        import uvicorn
        uvicorn.run('investigation.api:create_app', factory=True, host='127.0.0.1', port=8000, workers=1)
        return
    store = ContextStore(settings, Embeddings(settings))
    if args.command == 'index':
        result = store.build()
    else:
        store.validate(full_hash=True)
        result = Investigator(settings, store).investigate(args.question)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result.get('status') not in {None, 'complete'}:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
