"""Runner behavior tests. Synthetic diagnostics are not proof validation."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/universal.py"
SPEC = importlib.util.spec_from_file_location("universal_workflow", SCRIPT)
RUN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUN
SPEC.loader.exec_module(RUN)

FORMAL = Path('/tmp/workflow-log-tests')
TARGET = FORMAL / 'Formal/Example/Blueprint/Checks.lean'
SOURCE = ('import Formal.Universal.Properties\n'
          'theorem check_first : True := by blaster\n'
          'theorem check_second : True := by blaster\n')
VALID = "warning: declaration uses 'blasterProven' (SMT-verified, no proof term)"
FAMILY = RUN.Family('UP-test', 'unused')


def diagnostic(line, message, path=TARGET, col=35):
    return f'{path}:{line}:{col}: {message}\n'


class ReportingTests(unittest.TestCase):
    def parse(self, text, source=SOURCE):
        return RUN.parse_results(source, TARGET, FORMAL, text)

    def test_scoped_positive_and_negative_results(self):
        log = (diagnostic(2, VALID) + diagnostic(3, 'error: ❌ Falsified') +
               diagnostic(3, 'error: Counterexample:') + diagnostic(3, 'error:  - x: 2') +
               diagnostic(3, 'error: Tactic `blaster` failed: Goal was falsified (see counterexample above)'))
        raw, problems, _ = self.parse(log)
        self.assertEqual(raw['check_first']['verdict'], 'Valid')
        self.assertEqual(raw['check_second']['verdict'], 'Falsified')
        self.assertEqual(problems, [])

    def test_unscoped_and_other_file_success_cannot_supply_a_verdict(self):
        raw, _, _ = self.parse('✅ Valid\n' + diagnostic(2, VALID, Path('/tmp/elsewhere/Checks.lean')))
        self.assertTrue(all(r['verdict'] == 'NoResult' for r in raw.values()))

    def test_error_after_success_prevents_pass(self):
        raw, _, _ = self.parse(diagnostic(2, VALID) + diagnostic(2, 'error: unknown identifier'))
        self.assertEqual(raw['check_first']['verdict'], 'Error')

    def test_counterexample_does_not_hide_an_unrelated_error(self):
        raw, _, _ = self.parse(diagnostic(2, 'error: ❌ Falsified') + diagnostic(2, 'error: type mismatch'))
        self.assertEqual(raw['check_first']['verdict'], 'Error')
        self.assertEqual(raw['check_first']['solver_results'], ['Falsified'])

    def test_counterexample_detail_at_another_location_is_not_ignored(self):
        raw, _, _ = self.parse(diagnostic(2, 'error: ❌ Falsified') +
                               diagnostic(2, 'error: Counterexample:', col=40))
        self.assertEqual(raw['check_first']['verdict'], 'Error')

    def test_conflicting_solver_messages_are_inconclusive(self):
        raw, _, _ = self.parse(diagnostic(2, VALID) + diagnostic(2, 'error: ❌ Falsified'))
        self.assertEqual(raw['check_first']['verdict'], 'Error')

    def test_unexpected_sorry_prevents_pass(self):
        raw, _, _ = self.parse(diagnostic(2, VALID) + diagnostic(2, "warning: declaration uses 'sorry'"))
        self.assertEqual(raw['check_first']['verdict'], 'Error')

    def test_dependency_error_is_a_run_problem(self):
        raw, problems, _ = self.parse(diagnostic(2, VALID) +
                                     diagnostic(8, 'error: build failed', FORMAL / 'Dependency.lean'))
        self.assertEqual(raw['check_first']['verdict'], 'Valid')
        self.assertEqual(len(problems), 1)

    def test_missing_required_applicability_never_holds(self):
        for evidence in (None, 'NoResult', 'Error'):
            with self.subTest(evidence=evidence):
                self.assertEqual(RUN.interpret('Valid', 'Valid', evidence, True), 'INCONCLUSIVE')

    def test_proven_inapplicability_is_separate_from_pass(self):
        self.assertEqual(RUN.interpret('Valid', 'Valid', 'Falsified'), 'NOT_APPLICABLE')

    def test_disagreement_with_applicability_is_inconclusive(self):
        self.assertEqual(RUN.interpret('Falsified', 'Valid', 'Falsified'), 'INCONCLUSIVE')

    def test_expected_counterexample_can_supply_a_witness(self):
        self.assertEqual(RUN.interpret('Falsified', 'Falsified'), 'PASS')
        self.assertEqual(RUN.interpret('Valid', 'Falsified'), 'FAIL')

    def test_expected_counterexample_diagnostic_is_supported(self):
        raw, _, _ = self.parse(diagnostic(2, 'info: ✅ Expected Falsified'))
        self.assertEqual(raw['check_first']['verdict'], 'Falsified')

    def test_empty_and_mixed_runs_are_not_success(self):
        fail = {'result': 'FAIL', 'waived': False}
        pending = {'result': 'INCONCLUSIVE', 'waived': False}
        self.assertEqual(RUN.exit_code([], []), 2)
        self.assertEqual(RUN.exit_code([fail], []), 1)
        self.assertEqual(RUN.exit_code([fail, pending], []), 2)
        self.assertEqual(RUN.exit_code([dict(fail, waived=True)], ['timeout']), 2)


class WaiverTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = 'a' * 64
        self.item = {'blueprint_sha256': self.snapshot, 'reason': 'Reviewed intended behavior',
                     'owner': 'reviewer', 'until': '2026-10-27'}
        self.config = {'example.example': {'check_first': self.item}}

    def reviewed(self, result, **kwargs):
        row = {'check': 'check_first', 'result': result}
        return RUN.review_result(row, self.config, 'example.example',
                                 kwargs.get('snapshot', self.snapshot), kwargs.get('today', date(2026, 10, 27)))

    def test_known_failure_keeps_raw_result_with_valid_waiver(self):
        row = self.reviewed('FAIL')
        self.assertEqual(row['result'], 'FAIL')
        self.assertTrue(row['waived'])
        self.assertEqual(RUN.exit_code([row], []), 0)

    def test_known_inapplicability_requires_review(self):
        self.assertEqual(RUN.exit_code([{'result': 'NOT_APPLICABLE', 'waived': False}], []), 2)
        self.assertEqual(RUN.exit_code([self.reviewed('NOT_APPLICABLE')], []), 0)

    def test_expiry_date_is_inclusive_in_utc(self):
        self.assertTrue(self.reviewed('FAIL')['waived'])
        self.assertFalse(self.reviewed('FAIL', today=date(2026, 10, 28))['waived'])

    def test_snapshot_change_invalidates_waiver(self):
        row = self.reviewed('FAIL', snapshot='b' * 64)
        self.assertFalse(row['waived'])
        self.assertEqual(RUN.exit_code([row], []), 1)

    def test_inconclusive_result_cannot_be_waived(self):
        row = self.reviewed('INCONCLUSIVE')
        self.assertFalse(row['waived'])
        self.assertEqual(RUN.exit_code([row], []), 2)

    def test_waiver_does_not_apply_to_other_check(self):
        row = RUN.review_result({'check': 'other', 'result': 'FAIL'}, self.config,
                                'example.example', self.snapshot, date(2026, 10, 27))
        self.assertFalse(row['waived'])

    def test_configuration_rejects_missing_fields_and_expectation_overrides(self):
        invalid = [dict(self.item, expected='Falsified'), dict(self.item, until='2026-02-30'),
                   dict(self.item, owner=' '), dict(self.item, until='20261027'),
                   {key: value for key, value in self.item.items() if key != 'blueprint_sha256'}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'universal.json'
            path.write_text(json.dumps(self.config))
            self.assertEqual(RUN.load_waivers(path), self.config)
            for item in invalid:
                with self.subTest(item=item):
                    path.write_text(json.dumps({'example.example': {'check_first': item}}))
                    with self.assertRaises((RUN.WorkflowError, ValueError)):
                        RUN.load_waivers(path)


class ProcessTests(unittest.TestCase):
    def test_deadline_is_shared_across_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            deadline = time.monotonic() + 0.5
            first = RUN.command([sys.executable, '-c', 'print("ok")'], root, deadline, root / 'first.log')
            second = RUN.command([sys.executable, '-c', 'import time; time.sleep(5)'], root, deadline, root / 'second.log')
            self.assertEqual(first[:2], (0, False))
            self.assertTrue(second[1])
            with self.assertRaises(RUN.WorkflowError):
                RUN.command([sys.executable, '-c', 'print("late")'], root, deadline, root / 'late.log')

    @unittest.skipUnless(Path('/proc').exists(), 'Linux process-state probe')
    def test_timeout_stops_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code = ('import pathlib, subprocess, sys, time; '
                    'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"]); '
                    'pathlib.Path("child.pid").write_text(str(child.pid)); time.sleep(20)')
            pid = None
            try:
                result = RUN.command([sys.executable, '-c', code], root, time.monotonic() + 0.5, root / 'run.log')
                pid = int((root / 'child.pid').read_text())
                self.assertTrue(result[1])
                state = Path(f'/proc/{pid}/stat')
                limit = time.monotonic() + 1
                while state.exists() and state.read_text().split()[2] != 'Z' and time.monotonic() < limit:
                    time.sleep(0.01)
                self.assertTrue(not state.exists() or state.read_text().split()[2] == 'Z')
            finally:
                if pid is not None:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_invalid_timeout_values_fail(self):
        for value in ('0', '-1', 'nan', 'inf'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                RUN.positive_seconds(value)


class WorkflowTests(unittest.TestCase):
    """Exercise the real orchestration with synthetic generator/Lean process results."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.formal = self.root / 'formal'
        (self.formal / 'Formal').mkdir(parents=True)
        (self.formal / 'lake-manifest.json').write_text('{"packages": []}')
        (self.formal / 'lakefile.toml').write_text('name = "fixture"\n')
        (self.formal / 'lean-toolchain').write_text('leanprover/lean4:v4.24.0\n')
        self.external = self.root / 'external project'
        self.external.mkdir()
        self.bp = self.external / 'plutus.json'
        self.bp.write_text(json.dumps({'preamble': {'plutusVersion': 'v3'}, 'validators': [
            {'title': 'example.example.spend', 'compiledCode': '00'}]}))
        self.author = self.formal / 'Formal/Existing/Blueprint/Tx.lean'
        self.author.parent.mkdir(parents=True)
        self.author.write_text('-- keep author content\n')
        self.args = argparse.Namespace(blueprint=self.bp, validator='example', check='otherPurpose', config=None, timeout=30)
        self.commands = []
        self.mode = 'positive'
        self.captured_generator = b''

    def fake_command(self, args, cwd, deadline, log):
        self.commands.append(args)
        log.write_text('synthetic process log\n')
        if '--version' in args:
            if self.mode == 'tool-missing':
                raise FileNotFoundError('tool is missing')
            return 0, False, 'synthetic tool version'
        if '--check' in args:
            self.captured_generator = Path(args[3]).read_bytes()
            if self.mode == 'generation-error':
                return 1, False, 'generator failed'
            out = cwd / args[args.index('--out') + 1]
            out.mkdir(parents=True)
            text = ('import Formal.Universal.Properties\n'
                    'theorem otherPurpose_mint : True := by blaster\n')
            (out / 'Checks.lean').write_text(text if self.mode != 'empty' else '-- no obligations\n')
            return 0, False, ''
        if 'build' in args:
            if self.mode == 'interrupted':
                raise KeyboardInterrupt
            if self.mode == 'build-error':
                return 1, False, 'build failed'
            return 0, False, ''
        if self.mode == 'silent':
            return 0, False, ''
        if self.mode == 'timeout':
            return -9, True, ''
        message = 'error: ❌ Falsified' if self.mode == 'negative' else VALID
        return int(self.mode == 'negative'), False, diagnostic(2, message, Path(args[-1]))

    def execute(self):
        with patch.object(RUN.blueprint, 'other_purpose_checks', lambda: None, create=True), \
             patch.object(RUN, 'command', self.fake_command), redirect_stdout(io.StringIO()):
            code = RUN.run(self.args, self.formal)
        reports = sorted((self.formal / '.lake/universal').glob('run-*/report.json'))
        return code, json.loads(reports[-1].read_text())

    def test_external_snapshot_and_author_files_are_preserved(self):
        original = self.bp.read_bytes()
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report['results'][0]['result'], 'PASS')
        self.assertEqual(report['blueprint_sha256'], RUN.sha256(original))
        self.assertEqual(report['runner_sha256'], RUN.sha256(Path(RUN.__file__).read_bytes()))
        self.assertEqual(self.bp.read_bytes(), original)
        self.assertEqual(self.author.read_text(), '-- keep author content\n')
        self.assertFalse(list((self.formal / 'Formal').glob('WorkflowRun*')))
        self.assertFalse((self.formal / 'Scripts').exists())
        self.assertEqual(self.captured_generator, Path(RUN.blueprint.__file__).read_bytes())
        self.assertTrue(all('aiken' not in cmd and 'update' not in cmd for cmd in self.commands))

    def test_generation_failure_never_runs_lean(self):
        self.mode = 'generation-error'
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(report['results'], [])

    def test_empty_generation_cannot_pass(self):
        self.mode = 'empty'
        code, _ = self.execute()
        self.assertEqual(code, 2)
        self.assertEqual(len(self.commands), 1)

    def test_prerequisite_error_stops_before_checks(self):
        self.mode = 'build-error'
        code, _ = self.execute()
        self.assertEqual(code, 2)
        self.assertFalse(any('env' in cmd for cmd in self.commands))

    def test_successful_process_without_proof_is_inconclusive(self):
        self.mode = 'silent'
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertEqual(report['results'][0]['result'], 'INCONCLUSIVE')

    def test_timeout_is_never_success(self):
        self.mode = 'timeout'
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertTrue(report['problems'])

    def test_counterexample_has_nonzero_exit(self):
        self.mode = 'negative'
        code, report = self.execute()
        self.assertEqual(code, 1)
        self.assertEqual(report['results'][0]['result'], 'FAIL')

    def test_valid_snapshot_waiver_preserves_failure(self):
        self.mode = 'negative'
        config = self.formal / 'universal.json'
        config.write_text(json.dumps({'example.example': {'otherPurpose_mint': {
            'blueprint_sha256': RUN.sha256(self.bp.read_bytes()), 'reason': 'Reviewed fixture',
            'owner': 'reviewer', 'until': '9999-12-31'}}}))
        code, report = self.execute()
        self.assertEqual(code, 0)
        self.assertEqual(report['results'][0]['result'], 'FAIL')
        self.assertTrue(report['results'][0]['waived'])

    def test_missing_generator_fails_before_creating_artifacts(self):
        with patch.object(RUN.blueprint, 'other_purpose_checks', None, create=True), \
             self.assertRaisesRegex(RUN.WorkflowError, 'not available'):
            RUN.run(self.args, self.formal)
        self.assertFalse((self.formal / '.lake').exists())

    def test_interruption_leaves_an_inconclusive_report(self):
        self.mode = 'interrupted'
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertIn('interrupted', report['problems'][0])
        self.assertFalse(list((self.formal / 'Formal').glob('WorkflowRun*')))

    def test_missing_tool_is_an_execution_problem(self):
        self.mode = 'tool-missing'
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertIn('missing', report['problems'][0])

    def test_malformed_blueprint_returns_inconclusive_not_failure(self):
        for data in ([], {'preamble': []}, {'preamble': {'plutusVersion': 'v3'}, 'validators': [None]}):
            with self.subTest(data=data):
                self.bp.write_text(json.dumps(data))
                with patch.object(RUN.blueprint, 'other_purpose_checks', lambda: None, create=True), \
                     redirect_stderr(io.StringIO()):
                    self.assertEqual(RUN.main([str(self.bp), 'example', '--check', 'otherPurpose']), 2)

    def test_missing_dependency_does_not_fetch(self):
        (self.formal / 'lake-manifest.json').write_text(json.dumps({
            'packagesDir': '.lake/packages', 'packages': [{'type': 'git', 'name': 'Missing', 'rev': 'a' * 40}]}))
        code, report = self.execute()
        self.assertEqual(code, 2)
        self.assertEqual(self.commands, [])
        self.assertIn('missing', report['problems'][0])


if __name__ == '__main__':
    unittest.main()
