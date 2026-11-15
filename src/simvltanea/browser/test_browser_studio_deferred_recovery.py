"""A deferred loop-mode handoff must complete once its blocking condition clears.

Hosted macOS WebKit run 43688585931 (f7f45ba) toggled the loop mode, recorded
`handoff-deferred: Incoming frames did not become ready` for loop-1 and never
swapped loop-1 to the requested variant: nothing re-attempted the handoff, so
the cohort stayed mixed until the next edit. These tests force that timing with
the same fault the settlement suite uses (a primed successor whose play promise
resolves while its native element stays paused) and then add no further edit.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import unittest

from simvltanea.browser import test_browser_studio as studio_tests
from simvltanea.browser import test_browser_studio_settlement as settlement

BOOMERANG = "compositionRuntime.nodes.get('loop-1').item.asset.id"


class StudioDeferredRecoveryTests(unittest.TestCase):
    """Delegate fixture setup without collecting the settlement suite's tests."""

    @classmethod
    def setUpClass(cls):
        settlement.StudioSettlementTests.setUpClass.__func__(cls)
        # Two clips with a boomerang variant each, so one loop-mode toggle moves
        # two panels and the panels can fail for different reasons.
        two = studio_tests.LIBRARY_SITES / 'recovery-two'
        shutil.copytree(studio_tests.LIBRARY_SITES / 'settlement-variant', two)
        temporary = two / 'variant-two.mp4'
        studio_tests.ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=192x144:rate=30,hue=h=95',
                            '-f', 'lavfi', '-i', 'sine=frequency=521:sample_rate=48000',
                            '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-ac', '1', '-shortest', '-movflags', '+faststart', str(temporary))
        contents = temporary.read_bytes()
        variant_id = hashlib.sha256(contents).hexdigest()[:12]
        temporary.rename(two / 'library' / 'clips' / f'{variant_id}.mp4')
        manifest = json.loads((two / 'library' / 'manifest.json').read_text())
        first = next(item for item in manifest['clips'] if item['id'] == cls.ids[0])
        second = next(item for item in manifest['clips'] if item['id'] == cls.ids[1])
        second['variants'] = {'boomerang': {**first['variants']['boomerang'], 'id': variant_id,
                                            'file': f'clips/{variant_id}.mp4', 'bytes': len(contents)}}
        (two / 'library' / 'manifest.json').write_text(json.dumps(manifest))

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
        # The blocking condition clears (the stalled element plays again). No
        # further edit is made: the studio itself must re-attempt the handoff.
        page.evaluate('restoreSettlementFault()')
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

    def test_decode_failure_is_not_a_deferral_and_is_not_retried(self):
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        page.evaluate('''() => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.decodeFailures=0;
          r.prime=async (...args)=>{
            if(args[1].id==='loop-1') { decodeFailures++; throw new Error('Incoming clip could not be decoded'); }
            return prime(...args);
          };
        }''')
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => decodeFailures>=1', timeout=15000)
        self.settled(page)
        page.wait_for_timeout(7000)
        self.settled(page)
        self.assertEqual(page.evaluate('decodeFailures'), 1, 'a failing asset must not be retried')
        self.assertEqual(self.deferrals(page), 0)
        self.assertEqual(page.evaluate("compositionRuntime.events.filter(e=>e.type==='handoff-reattempt').length"), 0)
        self.assertEqual(self.loop_one_asset(page), boomerang)

    def test_only_the_deferred_slot_is_retried_when_a_sibling_fails_to_decode(self):
        page = self.ready(site='recovery-two')
        first = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        second = page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id")
        page.evaluate('''() => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.settlementFault={slot:'loop-1',applied:false,incoming:null};
          window.decodeFailures=0;
          r.prime=async (...args)=>{
            const [deck,node]=args;
            if(node.id==='loop-2') { decodeFailures++; throw new Error('Incoming clip could not be decoded'); }
            await prime(...args);
            if(node.id!=='loop-1' || settlementFault.applied) return;
            settlementFault.applied=true; settlementFault.incoming=deck.media;
            deck.media.pause(); deck.media.play=()=>Promise.resolve();
          };
          window.restoreSettlementFault=()=>{ if(settlementFault.incoming) delete settlementFault.incoming.play; };
        }''')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        page.wait_for_function(f"() => {BOOMERANG}==={first!r}", timeout=30000)
        self.settled(page)
        page.wait_for_timeout(5000)
        self.assertEqual(page.evaluate('decodeFailures'), 1, 'the failed sibling must not be retried with the deferred slot')
        self.assertEqual(page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id"), second)

    def test_repair_delay_uses_numeric_seconds_and_intent_ignores_playback_republish(self):
        page = self.ready(site='settlement-variant')
        delays = page.evaluate('''() => {
          const api=SimvltaneaStudio, item=(duration,seconds)=>({quantized:{duration,seconds}});
          return [api.repairDelayMs([]), api.repairDelayMs([item('13/2',6.5)]),
            api.repairDelayMs([item('2',2),item('7/2',3.5)]), api.repairDelayMs([item('60',60)])];
        }''')
        self.assertEqual(delays, [1000, 6500, 3500, 8000])
        same = page.evaluate('''() => {
          const api=SimvltaneaStudio, style={z1:'2'}, a={seed:7,family:'strips',style,loops:[0,1,2],retained:new Map()};
          const republished={...a,retained:new Map([[0,{}]])};
          return [api.sameIntent(a,republished), api.sameIntent(a,{...a,loops:[0,1,3]}),
            api.sameIntent(a,{...a,seed:8}), api.sameIntent(a,{...a,family:'authored'}),
            api.sameIntent(a,{...a,style:{z1:'2'}}), api.sameIntent(a,null)];
        }''')
        self.assertEqual(same, [True, False, False, False, False, False])

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

    def test_a_late_deferral_belongs_to_its_own_request_not_the_next_one(self):
        """Codex P2 (a3833f7): deferrals were counted cumulatively, so a request
        that recorded its deferral after the next launch had taken its snapshot
        lent that slot to the next launch. Hold request A's deferral until a
        second launch B has been submitted, then require the runtime to attribute
        the slot to A's revision and report none for B."""
        page = self.ready(site='settlement-variant')
        self.defer(page, 'loop-1')
        page.evaluate('''() => {
          const r=compositionRuntime, replace=r.replace.bind(r);
          window.heldDeferral={held:false,release:null,done:false};
          r.replace=async (...args)=>{
            if(heldDeferral.done) return replace(...args);
            heldDeferral.done=true;
            try { return await replace(...args); }
            catch(error) {
              heldDeferral.held=true;
              await new Promise(resolve=>{ heldDeferral.release=resolve; });
              throw error;
            }
          };
        }''')
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => heldDeferral.held', timeout=30000)
        revision_a = page.evaluate('compositionRuntime.revision')
        page.evaluate('restoreSettlementFault()')
        self.tap_panel(page, 'loop-2')
        page.wait_for_function('(a) => compositionRuntime.revision>a', arg=revision_a, timeout=15000)
        page.evaluate('heldDeferral.release()')
        self.settled(page)
        last = page.evaluate('compositionRuntime.lastDeferral')
        self.assertEqual(last['revision'], page.evaluate('compositionRuntime.revision'))
        self.assertEqual(last['slots'], [], 'request B deferred nothing; A\'s late deferral is not B\'s')
        self.assertEqual(self.deferrals(page), 1)
        page.wait_for_timeout(3000)
        self.assertEqual(page.evaluate("compositionRuntime.events.filter(e=>e.type==='handoff-reattempt').length"), 0)


    def test_edit_that_restores_the_same_intent_still_supersedes_the_re_attempt(self):
        """Cycling the family away and back is two edits that leave the intent
        equal to the one the repair was scheduled for (the same state a refused
        edit restores). The intent check alone cannot tell that apart from no
        edit, so each user edit must itself cancel the pending repair."""
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        key = "(s=>[s.seed,s.family,s.selection.join()].join('|'))(SimvltaneaStudio.snapshot())"
        before = page.evaluate(key)
        for _ in range(2):
            self.tap(page, '#families [aria-checked="true"]')
            page.wait_for_timeout(400)
        self.assertEqual(page.evaluate(key), before, 'the two edits must land on the same intent')
        self.settled(page)
        page.wait_for_timeout(12000)
        self.settled(page)
        self.assertEqual(page.evaluate("compositionRuntime.events.filter(e=>e.type==='handoff-reattempt').length"), 0)
        self.assertEqual(self.loop_one_asset(page), boomerang)


if __name__ == '__main__':
    unittest.main()
