"""Exercise real OCR, biometrics, decisions, persistence and optional live auditing."""
import argparse
import json
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--require-chain', action='store_true')
    args = parser.parse_args()
    samples = ROOT / 'backend/tests/demo_samples'
    fixtures = ROOT / 'backend/audit_demo/final-fixtures'
    evidence = []
    for scenario, document, selfie in [('clean', 'clean', 'astronaut_public_domain.png'),
            ('face_mismatch', 'clean', 'grace_hopper_public_domain.jpg'),
            ('blacklist', 'blacklist', 'astronaut_public_domain.png'),
            ('invalid', 'invalid', 'astronaut_public_domain.png')]:
        response = requests.post(args.api + '/api/screen', files={
            'file': (document + '.png', (fixtures / (document + '.png')).read_bytes(), 'image/png'),
            'selfie': (selfie, (samples / selfie).read_bytes(), 'image/jpeg' if selfie.endswith('.jpg') else 'image/png')},
            data={'document_type': 'passport'}, timeout=240)
        response.raise_for_status()
        case = response.json()
        reasons = [r['code'] for r in case['risk']['reasons']]
        summary = {'scenario': scenario, 'case_id': case['case_id'], 'document_type': case['document_type'],
                   'mrz_valid': case['mrz'].get('mrz_valid'), 'face': case['face']['status'],
                   'blacklisted': case['database']['blacklisted'], 'validation': case['validation']['status'],
                   'risk': case['risk'], 'identity_extracted': bool(case['ocr']['fields'].get('full_name'))}
        print(json.dumps(summary), flush=True)
        assert summary['identity_extracted'] and case['document_type'] == 'passport', summary
        if scenario == 'clean':
            assert case['mrz']['mrz_valid'] and case['face']['match'] is True, summary
            assert not case['database']['blacklisted'] and not case['tamper']['content_tamper_detected'], summary
            assert case['risk']['risk_level'] == 'LOW RISK' and case['risk']['recommendation'] == 'PROCEED_WITH_OFFICER_REVIEW', summary
        elif scenario == 'face_mismatch':
            assert case['face']['match'] is False and 'FACE_MISMATCH' in reasons, summary
        elif scenario == 'blacklist':
            assert case['database']['blacklisted'] and case['risk']['risk_level'] == 'CRITICAL', summary
        else:
            assert not case['mrz']['mrz_valid'] and 'MRZ_CHECK_FAILED' in reasons, summary
        url = args.api + '/api/cases/' + case['case_id']
        decision = 'APPROVED' if scenario == 'clean' else 'SECONDARY_INSPECTION'
        response = requests.post(url + '/decision', json={'decision': decision, 'remarks': 'Synthetic final demo validation', 'officer_id': 'DEMO-QA'}, timeout=60)
        response.raise_for_status()
        saved_response = requests.get(url, timeout=15)
        saved_response.raise_for_status()
        saved = saved_response.json()['case']
        assert saved['risk'] == case['risk'] and saved['officer_decision']['notes'] == 'Synthetic final demo validation'
        if args.require_chain:
            for _ in range(30):
                response = requests.get(url + '/audit', timeout=15)
                response.raise_for_status()
                records = response.json()['records']
                if len(records) == 2 and all(r['status'] in ('ANCHORED', 'VERIFIED') for r in records):
                    break
                time.sleep(1)
            assert len(records) == 2 and all(r['transaction_hash'] for r in records), records
            for kind in ['SCREENING_RESULT', 'OFFICER_DECISION']:
                response = requests.get(url + '/audit/verify', params={'record_type': kind}, timeout=30)
                response.raise_for_status()
                result = response.json()
                assert result['status'] == 'VERIFIED' and result['digest_match'] is True, result
            summary['audits'] = records
        evidence.append(summary)
    path = ROOT / 'backend/audit_demo/final-validation.json'
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('FINAL_DEMO_OK: 4 scenarios; evidence:', path)


if __name__ == '__main__':
    main()
