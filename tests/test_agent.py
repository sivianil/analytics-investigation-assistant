import json
import io
import subprocess
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd
from preprocess import clean, normalize_columns, run
from database import read_sqlite
from features import make_transformer
from sandbox import DockerSandbox, agent_loop

def sample():
    return pd.DataFrame({
        'Invoice':['001', 'C002', '003', '004', '005'],
        'StockCode':['007', '007', 'x', 'y', 'z'],
        'Description':['BANANA', 'NA', None, 'box', 'large'],
        'Quantity':[2, -1, 'bad', 1, 9999],
        'InvoiceDate':['2010-01-01']*5,
        'Price':[3, 3, 2, 0, 10],
        'Customer ID':['0001', None, 4.0, 'NA', '7'],
        'Country':['UK']*5})

class PreparationTests(unittest.TestCase):
    def test_default_preserves_return_missing_id_and_outlier(self):
        good, bad, report = clean(sample())
        self.assertEqual(len(good), 4)
        self.assertEqual(len(bad), 1)
        self.assertEqual(good.iloc[0].invoice, '001')
        self.assertEqual(good.iloc[0].stock_code, '007')
        self.assertEqual(good.iloc[0].description, 'BANANA')
        self.assertTrue(good.loc[1, 'is_return'])
        self.assertTrue(pd.isna(good.loc[1, 'customer_id']))
        self.assertTrue(good.loc[4, 'is_outlier'])
        self.assertEqual(report['conversion_failures']['quantity'], 1)

    def test_drop_any_missing_and_keep_policy(self):
        good, bad, report = clean(sample(), missing='any')
        self.assertEqual(len(good), 2)
        good, bad, _ = clean(sample(), missing='keep')
        self.assertEqual(len(good), 5)
        self.assertEqual(len(bad), 0)

    def test_duplicate_and_outlier_removal_are_opt_in(self):
        raw = pd.concat([sample(), sample().iloc[[0]]], ignore_index=True)
        good, _, r = clean(raw)
        self.assertEqual(r['duplicate_rows'], 1)
        self.assertEqual(len(good), 5)
        good, bad, r = clean(raw, deduplicate=True, outliers='drop')
        self.assertTrue('duplicate' in set(bad.rejection_reason))
        self.assertFalse(good.is_outlier.any())
        self.assertEqual(len(good)+len(bad), len(raw))

    def test_all_missing_infinity_and_numeric_dates(self):
        raw = sample()
        raw['Quantity'] = np.inf
        raw['InvoiceDate'] = 44000
        good, bad, report = clean(raw)
        self.assertEqual(len(good), 0)
        self.assertEqual(len(bad), 5)
        self.assertEqual(report['outlier_bounds']['quantity'], [None, None])
        self.assertEqual(report['conversion_failures']['invoice_date'], 5)

    def test_schema_drift_fails(self):
        raw = sample()
        raw['UnitPrice'] = raw.Price
        with self.assertRaises(ValueError):
            normalize_columns(raw)
        with self.assertRaises(ValueError):
            normalize_columns(sample().drop(columns='Country'))

    def test_export_and_row_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'input.csv'
            sample().to_csv(source, index=False)
            output = Path(tmp)/'output'
            report = run(source, output)
            rows = [json.loads(line) for line in (output/'cleaned.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), report['output_rows'])
            self.assertEqual(rows[0]['invoice'], '001')
            self.assertEqual(rows[1]['description'], None)
            with self.assertRaises(FileExistsError):
                run(source, output)

    def test_no_rejections_produces_empty_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'input.csv'
            sample().iloc[:1].to_csv(source, index=False)
            output = Path(tmp)/'output'
            run(source, output)
            self.assertEqual((output/'rejected.jsonl').read_bytes(), b'')

class FeatureTests(unittest.TestCase):
    def test_fitted_schema_stable_with_unknown_categories_and_missing(self):
        transform = make_transformer(['quantity'], ['country'], target='future_value')
        train = pd.DataFrame({'quantity':[1, 3, np.nan], 'country':['UK', 'UK', np.nan]})
        x = transform.fit_transform(train)
        y = transform.transform(pd.DataFrame({'quantity':[999, np.nan], 'country':['NEW', np.nan]}))
        self.assertEqual(x.shape[1], y.shape[1])
        self.assertEqual(transform.named_transformers_['numeric']['impute'].statistics_[0], 2)
        self.assertTrue(np.isfinite(y.toarray() if hasattr(y, 'toarray') else y).all())

    def test_target_exclusion(self):
        with self.assertRaises(ValueError):
            make_transformer(['quantity'], ['country'], target='quantity')

class DatabaseTests(unittest.TestCase):
    def test_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.db'
            with sqlite3.connect(path) as conn:
                conn.execute('create table example (n integer)')
                conn.executemany('insert into example values (?)', [(1,), (2,)])
            self.assertEqual(len(read_sqlite(path, 'select * from example', limit=1)), 1)
            with self.assertRaises(sqlite3.DatabaseError):
                read_sqlite(path, 'delete from example')
            with self.assertRaises(sqlite3.DatabaseError):
                read_sqlite(path, "attach database ':memory:' as extra")

class AgentTests(unittest.TestCase):
    def test_container_controls_and_cleanup_on_timeout(self):
        proc = MagicMock()
        proc.stdout = io.BytesIO(b'partial output')
        proc.wait.side_effect = [subprocess.TimeoutExpired('docker', 1), 137]
        proc.poll.return_value = None
        proc.returncode = 137
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)/'data.jsonl'
            data.write_text('{}\n')
            with patch('sandbox.shutil.which', return_value='/bin/docker'), \
                 patch('sandbox.subprocess.Popen', return_value=proc) as launch, \
                 patch('sandbox.subprocess.run') as cleanup:
                result = DockerSandbox(timeout=1).execute('print(1)', data)
                command = launch.call_args.args[0]
                for flag in ['--network=none', '--read-only', '--cap-drop=ALL',
                             '--security-opt=no-new-privileges:true', '--user=65534:65534',
                             '--memory=2g', '--pids-limit=64', '--pull=never']:
                    self.assertIn(flag, command)
                self.assertTrue(result['timed_out'])
                self.assertEqual(cleanup.call_args.args[0][:3], ['docker', 'rm', '-f'])
                proc.kill.assert_called_once()

    def test_no_host_fallback(self):
        with patch('sandbox.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'refusing'):
                DockerSandbox().execute('print(1)', 'anything')

    def test_error_repair_loop(self):
        class FakeSandbox:
            def execute(self, code, path):
                return {'exit_code':0 if code=='print(2)' else 1, 'timed_out':False,
                        'output':'2' if code=='print(2)' else 'NameError', 'truncated':False}
        responses = iter([{'action':'python','code':'bad'}, {'action':'python','code':'print(2)'},
                          {'action':'final','answer':'2'}])
        seen = []
        def model(messages):
            seen.append(str(messages))
            return next(responses)
        result = agent_loop('Count', model, 'data', sandbox=FakeSandbox())
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['trace']), 2)
        self.assertIn('NameError', seen[1])

    def test_loop_is_bounded_and_final_requires_observation(self):
        result = agent_loop('Count', lambda _: {'action':'final','answer':'invented'}, 'data', max_steps=2)
        self.assertEqual(result['status'], 'step_limit')

if __name__ == '__main__':
    unittest.main()
