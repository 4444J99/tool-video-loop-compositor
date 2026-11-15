"""A deferred loop-mode handoff must complete once its blocking condition clears.

Hosted macOS WebKit run 43688585931 (f7f45ba) toggled the loop mode, recorded
`handoff-deferred: Incoming frames did not become ready` for loop-1 and never
swapped loop-1 to the requested variant: nothing re-attempted the handoff, so
the cohort stayed mixed until the next edit. These tests force that timing with
the same fault the settlement suite uses (a primed successor whose play promise
resolves while its native element stays paused) and then add no further edit.
"""
from __future__ import annotations

import unittest

from simvltanea.browser import test_browser_studio_settlement as settlement

BOOMERANG = "compositionRuntime.nodes.get('loop-1').item.asset.id"


class StudioDeferredRecoveryTests(unittest.TestCase):
    """Delegate fixture setup without collecting the settlement suite's tests."""

    @classmethod
    def setUpClass(cls):
        settlement.StudioSettlementTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        settlement.StudioSettlementTests.tearDownClass.__func__(cls)

    open = settlement.StudioSettlementTests.open
    snapshot = settlement.StudioSettlementTests.snapshot
    playing = settlement.StudioSettlementTests.playing
    unlock = settlement.StudioSettlementTests.unlock
    tap = settlement.StudioSettlementTests.tap
    ready = settlement.StudioSettlementTests.ready
    settled = settlement.StudioSettlementTests.settled
    defer = settlement.StudioSettlementTests.defer
    tap_panel = settlement.StudioSettlementTests.tap_panel
    wait_deferred = settlement.StudioSettlementTests.wait_deferred
    report = settlement.StudioSettlementTests.report
    assert_plan_matches_residents = settlement.StudioSettlementTests.assert_plan_matches_residents

    def persistent_defer(self, page, slot='loop-1'):
        """Every incoming clip for the slot stays paused: the condition never clears."""
        page.evaluate('''slot => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.settlementFault={slot,applied:false,incoming:null,count:0};
          r.prime=async (...args)=>{
            await prime(...args);
            const [deck,node]=args;
            if(node.id!==slot) return;
            settlementFault.count++; settlementFault.incoming=deck.media;
            settlementFault.itemName=deck.item.name;
            deck.media.pause(); deck.media.play=()=>Promise.resolve();
          };
        }''', slot)

    def deferrals(self, page):
        return page.evaluate("compositionRuntime.events.filter(e=>e.type==='handoff-deferred').length")

    def loop_one_asset(self, page):
        return page.evaluate(f'({BOOMERANG})')

    def test_loop_mode_toggle_deferral_recovers_without_another_edit(self):
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        self.assertEqual(self.loop_one_asset(page), boomerang)
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        self.assertEqual(page.evaluate('SimvltaneaStudio.snapshot().loopMode'), 'forward')
        # The fault applies to the first incoming clip only: the condition has
        # cleared by the time a bounded re-attempt runs. No edit is made here.
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        result = self.report(page, 'deferred-loop-mode-recovery')
        self.assertEqual(len(result['deferred']), 1, 'one deferral, then one successful re-attempt')
        self.assertIsNone(result['failure'])
        self.assertEqual(result['snapshot']['loopMode'], 'forward')
        self.assertTrue(all(page.evaluate(
            "[...compositionRuntime.nodes.values()].map(n=>n.item.asset.id===n.item.clip.id)")))
        self.assertEqual(result['permits'], 0)
        self.assertTrue(result['context'] and result['clock'] and result['generation'])
        # Siblings were never replaced and still advance; the studio kept running.
        for sibling in result['residents'][1:]:
            self.assertTrue(all(sibling[key] for key in ('sameNode', 'sameMedia', 'sameDeck', 'sameItem',
                'sameBirth', 'sameAudio', 'sameURL', 'advancing')), sibling)
        self.assert_plan_matches_residents(result)

    def test_persistent_blocking_condition_stops_after_bounded_attempts(self):
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        self.persistent_defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        # One deferral for the toggle plus at most two bounded re-attempts.
        page.wait_for_function(
            "() => compositionRuntime.events.filter(e=>e.type==='handoff-deferred').length>=3", timeout=60000)
        self.settled(page)
        page.wait_for_timeout(7000)
        self.settled(page)
        self.assertEqual(self.deferrals(page), 3)
        self.assertEqual(self.loop_one_asset(page), boomerang, 'a persistent fault keeps the exact old variant')
        self.assertEqual(page.evaluate('SimvltaneaStudio.snapshot().loopMode'), 'forward')
        self.assertTrue(page.evaluate('compositionRuntime.ready'))
        self.assertTrue(page.evaluate(
            "[...compositionRuntime.nodes.values()].every(n=>!n.media.paused)"))

    def test_next_edit_supersedes_the_pending_re_attempt(self):
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        self.tap_panel(page, 'loop-2')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-2').item!==settlementBefore.residents[1].item")
        self.settled(page)
        page.wait_for_timeout(8000)
        self.settled(page)
        self.assertEqual(self.loop_one_asset(page), boomerang,
                         'a newer intent owns the field; the stale re-attempt must not replace the retained variant')
        self.assertEqual(self.deferrals(page), 1)


if __name__ == '__main__':
    unittest.main()
