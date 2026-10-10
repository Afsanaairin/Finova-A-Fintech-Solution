"""Test FINOVA's evidence and fail-open financial Q&A without live credentials."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


class FinovaV3Tests(unittest.TestCase):
    def test_anomaly_evidence_matches_ledger(self):
        sample = server.DEFAULT_RESULT
        spike = next(a for a in sample['anomalies'] if a['category']=='Electricity' and a['month']=='2026-06')
        self.assertTrue(spike['evidence'])
        self.assertAlmostEqual(sum(t['amount'] for t in spike['evidence']), spike['amount'], places=2)
        self.assertGreater(spike['amount'], spike['baseline'])
        self.assertTrue(spike['method'] and spike['action'])

    def test_401_fallback_can_answer_local_financial_question(self):
        with patch.object(server,'akamai_configured',return_value=True):
            with patch.object(server,'ai_answer',side_effect=RuntimeError('Akamai rejected the team key (HTTP 401).')):
                # endpoint-level case is exercised in the smoke test script
                answer=server.offline_answer('Why have expenses changed?',server.DEFAULT_RESULT)
        self.assertIn('Payments changed by', answer)
        self.assertIn('Office Supplies', answer)

    def test_explicit_alert_answer_refers_to_correct_month(self):
        ans=server.offline_answer('Explain the Spending spike for Electricity in 2026-06 and what we should check.',server.DEFAULT_RESULT)
        self.assertIn('2026-06',ans)
        self.assertIn('1,166.39',ans)
        self.assertIn('716.43',ans)

    def test_env_values_prefer_project_env_over_inherited_shell(self):
        # Use a temporary private folder so no actual credentials are touched.
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'.env').write_text('OPENAI_API_KEY=hk_from_file\nOPENAI_BASE_URL=https://ws.akamai-workshops.com/v1\n')
            with patch.object(server,'BASE',Path(temp)):
                with patch.dict(os.environ, {'OPENAI_API_KEY':'hk_old_shell_key'}):
                    self.assertEqual(server.config()['OPENAI_API_KEY'],'hk_from_file')


if __name__=='__main__':unittest.main()