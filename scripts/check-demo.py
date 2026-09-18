"""Probe a running demo without exposing configuration secrets."""
import argparse
import sys
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--frontend', default='http://127.0.0.1:5173')
    parser.add_argument('--warmup', action='store_true', help='Initialize OCR and face models on the backend')
    args = parser.parse_args()
    failed = False
    try:
        response = requests.get(args.api + '/health', timeout=10)
        response.raise_for_status()
        print('Backend: OK')
        response = requests.get(args.api + '/health/readiness', params={'warmup': str(args.warmup).lower()}, timeout=120)
        response.raise_for_status()
        state = response.json()
        print('Database:', state['database'])
        print('OCR:', state['ocr'], '(' + state['ocr_engine'] + ')')
        print('Face Service:', state['face'])
        chain = state['blockchain']
        print('Blockchain RPC:', 'OK' if chain['rpc_reachable'] else 'OFFLINE (optional)' if chain['enabled'] else 'DISABLED (optional)')
        print('Audit Contract:', 'OK' if chain['contract_reachable'] else 'UNAVAILABLE (optional)')
        failed = state['status'] == 'NOT_READY'
        status = state['status'].replace('_', ' ')
    except requests.RequestException:
        print('Backend readiness: UNAVAILABLE')
        failed, status = True, 'NOT READY'
    try:
        requests.get(args.frontend, timeout=10).raise_for_status()
        print('Frontend: OK')
    except requests.RequestException:
        print('Frontend: UNAVAILABLE')
        failed, status = True, 'NOT READY'
    print('Application status:', status)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
