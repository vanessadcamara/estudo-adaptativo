"""Independent weekly FSRS-6 optimization worker; never imported by request handlers.

Production: python -m app.optimize_retention --apply
Default: dry run with no database writes.
"""
from __future__ import annotations
import argparse
import json
import sys
from app.db import session_factory
from app.full_fsrs_optimizer import optimize_profiles


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Otimização completa FSRS fora do servidor web')
    parser.add_argument('--apply', action='store_true', help='Gravar modelos aprovados no banco configurado')
    parser.add_argument('--scope', default=None, help='Ex.: topic:1 ou question:1')
    args = parser.parse_args(argv)
    try:
        with session_factory()() as session:
            results = optimize_profiles(session, scope_filter=args.scope, dry_run=not args.apply)
        for result in results:
            print(json.dumps(result, ensure_ascii=False))
        if not results:
            print('Nenhuma matéria com histórico elegível.')
        return 0
    except (ImportError, RuntimeError, ValueError) as error:
        print(f'Otimização não concluída: {type(error).__name__}: {str(error)[:200]}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
