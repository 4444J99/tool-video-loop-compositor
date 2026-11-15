"""Attribution of stalls to the page or to the host observer (issue 115); no browser required."""
from __future__ import annotations

import json
from pathlib import Path
from simvltanea import subprocess_retry as retry
import unittest

from simvltanea.browser.test_webkit_verifier import FIXTURE, NATIVE_PROGRESS, VERIFIER

MODULE = Path(__file__).with_name('webkit_sampler_diagnostics.js')


def run(program: str, *arguments: str) -> dict:
    completed = retry.run(['node', '-e', program, *arguments], check=True, capture_output=True, text=True, timeout=15)
    return json.loads(completed.stdout)


ROWS = r'''
const diagnostics = require(process.argv[1]);
const deck = (id, callbacks, frames, extra = {}) => ({id, deck: 0, populated: true, paused: false, ready: 4,
  seeking: false, callbacks, quality: {totalVideoFrames: frames}, ...extra});
const row = (wall, sim, cbs, extra = {}) => ({wall, simTime: sim, epochMs: 1000000 + wall,
  decks: cbs.map((callbacks, index) => deck('loop-' + index, callbacks, callbacks)), ...extra});
'''


class SamplerGapTests(unittest.TestCase):
    def test_gap_with_a_live_page_is_attributed_to_the_observer(self):
        out = run(ROWS + r'''
const a = row(25592, 24.569, [606, 589]), b = row(27660, 26.586, [645, 640]);
b.runner = {sentAtMs: 1000000 + 25600, returnedAtMs: 1000000 + 27662};
process.stdout.write(JSON.stringify(diagnostics.samplerGaps([a, b])));
''', str(MODULE))
        self.assertEqual(out['count'], 1)
        gap = out['gaps'][0]
        self.assertEqual(gap['gapMs'], 2068)
        self.assertTrue(gap['pageAlive'], gap)
        self.assertEqual(gap['simAdvancedMs'], 2017)
        self.assertEqual(gap['callbackDelta'], 90)
        # The page ran the sample 2060 ms after the request left the runner and answered within 2 ms.
        self.assertEqual((gap['dispatchMs'], gap['returnMs']), (2060, 2))
        self.assertEqual(out['pageAliveCount'], 1)

    def test_gap_with_a_stopped_page_is_not_attributed_to_the_observer(self):
        for label, later in (('clock frozen', [645, 640]), ('no callbacks', [606, 589])):
            with self.subTest(label):
                sim = 24.6 if label == 'clock frozen' else 26.586
                out = run(ROWS + f'''
const a = row(25592, 24.569, [606, 589]), b = row(27660, {sim}, {json.dumps(later)});
process.stdout.write(JSON.stringify(diagnostics.samplerGaps([a, b])));
''', str(MODULE))
                self.assertFalse(out['gaps'][0]['pageAlive'], out)
                self.assertEqual(out['pageAliveCount'], 0)

    def test_short_gaps_and_missing_stamps_are_quiet(self):
        out = run(ROWS + r'''
process.stdout.write(JSON.stringify(diagnostics.samplerGaps([row(0, 0, [1]), row(900, .9, [30]), row(1900, 1.9, [60])])));
''', str(MODULE))
        self.assertEqual(out['count'], 0)
        self.assertEqual(out['maxGapMs'], 0)
        out = run(ROWS + r'''
process.stdout.write(JSON.stringify(diagnostics.samplerGaps([row(0, 0, [1]), row(1200, 1.2, [40])])));
''', str(MODULE))
        self.assertIsNone(out['gaps'][0]['dispatchMs'])

    def test_observe_stamps_both_runner_clocks_around_the_evaluate(self):
        out = run(r'''
const {observe} = require(process.argv[1]);
const page = {evaluate: async (fn, arg) => { await new Promise(r => setTimeout(r, 30)); return fn(arg); }};
observe(page, arg => ({epochMs: Date.now(), arg}), 7).then(row => {
  process.stdout.write(JSON.stringify({arg: row.arg, ordered: row.runner.sentAtMs <= row.epochMs && row.epochMs <= row.runner.returnedAtMs,
    spanMs: row.runner.returnedAtMs - row.runner.sentAtMs}));
});
''', str(MODULE))
        self.assertEqual(out['arg'], 7)
        self.assertTrue(out['ordered'])
        self.assertGreaterEqual(out['spanMs'], 25)


class DecodeFreezeTests(unittest.TestCase):
    def test_every_deck_flat_for_seconds_is_reported_with_onset_context(self):
        out = run(ROWS + r'''
const rows = [];
for (let i = 0; i < 12; i++) rows.push(row(i * 400, i * .4, [i * 10, i * 10]));
const frozen = [];
for (let i = 12; i < 36; i++) frozen.push(row(i * 400, i * .4, [120, 120]));
frozen[0].decks[0].seeking = true;
process.stdout.write(JSON.stringify(diagnostics.decodeFreezes([...rows, ...frozen])));
''', str(MODULE))
        self.assertEqual(out['count'], 1)
        window = out['windows'][0]
        self.assertGreaterEqual(window['durationMs'], 9000)
        self.assertEqual(window['seekingDecksAtOnset'], 1)
        self.assertGreater(window['simAdvancedMs'], 9000)

    def test_one_advancing_deck_or_a_paused_page_is_not_a_freeze(self):
        out = run(ROWS + r'''
const rows = [];
for (let i = 0; i < 20; i++) rows.push(row(i * 400, i * .4, [120, i * 10]));
const paused = [];
for (let i = 0; i < 20; i++) { const r = row(i * 400, i * .4, [120, 120]); r.decks.forEach(d => { d.paused = true; }); paused.push(r); }
process.stdout.write(JSON.stringify({advancing: diagnostics.decodeFreezes(rows), paused: diagnostics.decodeFreezes(paused)}));
''', str(MODULE))
        self.assertEqual(out['advancing']['count'], 0)
        self.assertEqual(out['paused']['count'], 0)

    def test_total_decoded_frames_count_as_progress(self):
        out = run(ROWS + r'''
const rows = [];
for (let i = 0; i < 20; i++) { const r = row(i * 400, i * .4, [120, 120]); r.decks[0].quality.totalVideoFrames = 500 + i; rows.push(r); }
process.stdout.write(JSON.stringify(diagnostics.decodeFreezes(rows)));
''', str(MODULE))
        self.assertEqual(out['count'], 0)


class AnalyseCarriesDiagnosticsTests(unittest.TestCase):
    def analyse(self, mutation: str = '') -> dict:
        return run(FIXTURE + NATIVE_PROGRESS + mutation + '\nprocess.stdout.write(JSON.stringify(require(process.argv[1]).analyse(result)));',
                   str(VERIFIER))

    def test_diagnostics_are_reported_and_never_gate_the_verdict(self):
        baseline = self.analyse()
        self.assertIn('diagnostics', baseline)
        self.assertEqual(baseline['diagnostics']['decodeFreezes']['count'], 0)
        # A 2 s hole in the samples and a flat-decoder window are both attributed, and neither changes pass/verdict/checks.
        mutated = self.analyse(r'''
result.samples.splice(700, 14);
for (const row of result.samples.slice(300, 330)) for (const node of row.nodes) node.callbacks = 7;
''')
        self.assertEqual(mutated['diagnostics']['samplerGaps']['count'], 1)
        self.assertEqual(mutated['diagnostics']['prelude']['samplerGaps']['count'], 0)
        self.assertEqual((mutated['pass'], mutated['verdict']), (baseline['pass'], baseline['verdict']))
        gated = lambda summary: {key: value for key, value in summary['checks'].items() if key != 'observationCoverage'}
        self.assertEqual(gated(mutated), gated(baseline))

    def test_prelude_samples_are_attributed_separately(self):
        out = self.analyse(r'''
result.prelude = {samples: Array.from({length: 20}, (_, i) => ({wall: i * 400, simTime: i * .4,
  decks: [{id: 'loop-1', deck: 0, populated: true, paused: false, ready: 4, callbacks: 9, quality: {totalVideoFrames: 9}}]}))};
''')
        self.assertEqual(out['diagnostics']['prelude']['decodeFreezes']['count'], 1)
        self.assertEqual(out['diagnostics']['decodeFreezes']['count'], 0)


if __name__ == '__main__':
    unittest.main()
