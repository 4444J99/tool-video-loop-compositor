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
from simvltanea.browser.silent_browser import init_script as silent_init_script

BOOMERANG = "compositionRuntime.nodes.get('loop-1').item.asset.id"
REATTEMPTS = "compositionRuntime.events.filter(e=>e.type==='handoff-reattempt')"

# Stands in for the evolve engine: its own requests are dropped and a replacement
# of the named slot is issued on demand through the same request path the studio
# serves for a real evolve (a sibling replacement is a playback-only relaunch).
EVOLVE_HOOK = '''(() => {
  let engine;
  Object.defineProperty(window, 'SimvltaneaEcosystem', {configurable: true, get: () => engine, set(value) {
    engine = value;
    const step = value.Engine.prototype.step;
    value.Engine.prototype.step = function(...args) {
      const out = step.apply(this, args);
      out.requests.length = 0;
      if (window.forceReplace !== null && window.forceReplace !== undefined) {
        out.requests.push({type: 'replace', id: `loop-${window.forceReplace + 1}`, index: window.forceReplace,
          clipKey: 'forced', serial: -1});
        window.forceReplace = null;
      }
      return out;
    };
  }});
})();'''


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
        # The second clip is seven seconds long, so the deferred first panel's own
        # loop (about two seconds) and the longest resident's loop differ widely.
        long = studio_tests.LIBRARY_SITES / 'recovery-long'
        shutil.copytree(studio_tests.LIBRARY_SITES / 'settlement-variant', long)
        temporary = long / 'long.mp4'
        studio_tests.ffmpeg('-f', 'lavfi', '-i', 'testsrc2=size=192x144:rate=24,hue=h=140',
                            '-f', 'lavfi', '-i', 'sine=frequency=419:sample_rate=48000',
                            '-t', '7', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-ac', '1', '-shortest', '-movflags', '+faststart', str(temporary))
        contents = temporary.read_bytes()
        long_id = hashlib.sha256(contents).hexdigest()[:12]
        temporary.rename(long / 'library' / 'clips' / f'{long_id}.mp4')
        manifest = json.loads((long / 'library' / 'manifest.json').read_text())
        # The mix selects by manifest position: test_retry_delay... puts position 6 in loop-2.
        index = cls.long_position = 6
        manifest['clips'][index] = {**manifest['clips'][index], 'id': long_id, 'file': f'clips/{long_id}.mp4',
                                    'bytes': len(contents), 'duration_seconds': 7.0, 'width': 192, 'height': 144,
                                    'orientation': 'landscape'}
        (long / 'library' / 'manifest.json').write_text(json.dumps(manifest))

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

    def open_held(self, site='settlement-variant'):
        """A reduced-motion visit starts held: `hold` is only ever true from load until the first play."""
        context = self.browser.new_context(viewport={'width': 1280, 'height': 720}, has_touch=True,
                                           reduced_motion='reduce')
        self.addCleanup(context.close)
        page = context.new_page()
        page.errors = []
        page.on('pageerror', lambda error: page.errors.append(str(error)))
        page.add_init_script(silent_init_script() + '\n' + settlement.COMPILER_OBSERVER)
        page.goto(f'{self.origin}/{site}/watch.html?seed=99&mix=s0.1.2.3&evolve=0&proof=1')
        page.wait_for_function('() => window.SimvltaneaStudio && window.compositionRuntime && '
                               'SimvltaneaStudio.snapshot().seed !== null && SimvltaneaStudio.snapshot().held && '
                               'compositionRuntime.ready && compositionRuntime.nodes.size === 4')
        self.addCleanup(lambda: self.assertEqual(page.errors, []))
        self.settled(page)
        return page

    def reattempts(self, page):
        return page.evaluate(f"{REATTEMPTS}.map(e=>({{slots:e.slots,remaining:e.remaining}}))")

    def wait_reattempts(self, page, count, timeout=30000):
        page.wait_for_function(f'count => {REATTEMPTS}.length>=count', arg=count, timeout=timeout)

    def pause_page(self, page):
        self.tap(page, '#play')
        page.wait_for_function('() => SimvltaneaStudio.snapshot().paused')

    def resume_page(self, page):
        self.tap(page, '#play')
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().paused')

    def force_replace(self, page, slot_index):
        page.evaluate('index => { window.forceReplace = index; }', slot_index)
        page.wait_for_function('() => window.forceReplace === null', timeout=15000)

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
        self.assertEqual(self.reattempts(page), [{'slots': [0], 'remaining': 1}, {'slots': [0], 'remaining': 0}],
                         'exactly two bounded re-attempts, each naming the deferred slot and the attempts left')
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

    def test_edit_that_keeps_the_slot_replaces_the_deferred_panel_itself(self):
        """Issue 126. The edit supersedes the pending re-attempt, and it must not
        leave the old variant behind: its own launch replaces the deferred panel."""
        page = self.ready(site='settlement-variant')
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        self.tap_panel(page, 'loop-2')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-2').item!==settlementBefore.residents[1].item")
        self.settled(page)
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        page.wait_for_timeout(5000)
        self.assertEqual(self.loop_one_asset(page), forward,
                         'an edit that keeps the slot must not leave the old variant for good')
        self.assertEqual(self.deferrals(page), 1)
        self.assertEqual(self.reattempts(page), [], 'the edit replaced the panel itself; no timer re-attempt')

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
          // Every write to lastDeferral, in order: the attribution itself.
          let current=r.lastDeferral; window.deferralWrites=[];
          Object.defineProperty(r,'lastDeferral',{configurable:true,get:()=>current,
            set:value=>{ deferralWrites.push(structuredClone(value)); current=value; }});
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
        writes = page.evaluate('deferralWrites')
        self.assertEqual([(w['revision'], w['slots']) for w in writes[-2:]],
                         [(revision_a, ['loop-1']), (last['revision'], [])],
                         'the late deferral is recorded under its own request\'s revision, ahead of the next request\'s')
        self.assertEqual(self.deferrals(page), 1)
        page.wait_for_timeout(3000)
        self.assertEqual(page.evaluate("compositionRuntime.events.filter(e=>e.type==='handoff-reattempt').length"), 0)


    def test_edit_that_restores_the_same_intent_leaves_no_old_variant_and_no_re_attempt(self):
        """Cycling the family away and back is two edits that leave the intent
        equal to the one the repair was scheduled for. Each edit replaces the
        deferred panel in its own launch, so the field is not left mixed."""
        page = self.ready(site='settlement-variant')
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
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
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        page.wait_for_timeout(5000)
        self.assertEqual(self.reattempts(page), [])
        self.assertEqual(self.loop_one_asset(page), forward)

    def test_edit_cancels_the_pending_re_attempt_even_when_its_own_launch_defers_again(self):
        """The edit owns the field: the toggle's timer must not fire after it, even
        though the edit's launch re-deferred the same panel (the same retained
        entry the timer is keyed to)."""
        page = self.ready(site='settlement-variant')
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        page.evaluate('compositionRuntime.progressTimeoutMs = 400')
        self.persistent_defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        self.tap(page, '#families [aria-checked="true"]')
        page.wait_for_function(
            "() => compositionRuntime.events.filter(e=>e.type==='handoff-deferred').length>=2", timeout=30000)
        self.settled(page)
        page.wait_for_timeout(8000)
        self.settled(page)
        self.assertEqual(self.deferrals(page), 2, 'the toggle and the edit; the edit is not retried')
        self.assertEqual(self.reattempts(page), [])
        self.assertEqual(self.loop_one_asset(page), boomerang)

    def test_an_edit_does_not_retry_a_sibling_that_failed_to_decode(self):
        """Only readiness deferrals are replaced by an edit: a retained entry left by
        a decode failure is not transient and stays, whatever the edit."""
        page = self.ready(site='recovery-two')
        first = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        second = page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id")
        page.evaluate('''() => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.decodeFailures=0;
          r.prime=async (...args)=>{
            if(args[1].id==='loop-2') { decodeFailures++; throw new Error('Incoming clip could not be decoded'); }
            return prime(...args);
          };
        }''')
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => decodeFailures>=1', timeout=15000)
        self.settled(page)
        page.wait_for_function(f"() => {BOOMERANG}==={first!r}", timeout=30000)
        self.tap_panel(page, 'loop-3')
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-3').item!==settlementBefore.residents[2].item")
        self.settled(page)
        page.wait_for_timeout(3000)
        self.assertEqual(page.evaluate('decodeFailures'), 1, 'an edit must not re-prime a known-bad asset')
        self.assertEqual(page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id"), second)

    def test_sibling_replacement_inside_the_retry_window_keeps_the_re_attempt(self):
        """Issue 127. A sibling replaced while the retry is pending (evolve) changes
        the loops but not the deferred panel's retained entry."""
        page = self.ready(site='settlement-variant', init_script=EVOLVE_HOOK)
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        self.force_replace(page, 1)
        page.wait_for_function("() => compositionRuntime.nodes.get('loop-2').item!==settlementBefore.residents[1].item")
        self.wait_reattempts(page, 1)
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        self.assertEqual(self.reattempts(page), [{'slots': [0], 'remaining': 1}])

    def test_unholding_while_the_toggles_launch_is_in_flight_keeps_the_remaining_attempts(self):
        """Issue 128, through the real trigger: the play control's unhold relaunch
        (playback-only, no retry budget of its own) lands while the toggle's own
        launch is still priming, supersedes it, and itself defers the panel."""
        page = self.open_held()
        boomerang = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.variants.boomerang.id")
        page.evaluate('''() => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.settlementFault={count:0}; window.primeGate=null; window.gated=false;
          r.prime=async (...args)=>{
            const [deck,node]=args;
            if(node.id==='loop-1' && !gated) { gated=true; await new Promise(resolve=>{ primeGate=resolve; }); }
            await prime(...args);
            if(node.id!=='loop-1') return;
            settlementFault.count++; deck.media.pause(); deck.media.play=()=>Promise.resolve();
          };
        }''')
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => gated', timeout=15000)
        self.tap(page, '#play')
        page.wait_for_function('() => !SimvltaneaStudio.snapshot().held', timeout=15000)
        page.evaluate('primeGate()')
        self.wait_reattempts(page, 2, timeout=60000)
        self.settled(page)
        page.wait_for_timeout(4000)
        self.assertEqual(self.reattempts(page), [{'slots': [0], 'remaining': 1}, {'slots': [0], 'remaining': 0}])
        self.assertEqual(self.loop_one_asset(page), boomerang)

    def test_retry_delay_is_the_deferred_panels_own_loop_not_the_longest_residents(self):
        """Issue 129. Loop-2 is seven seconds long; the deferred loop-1 about two."""
        page = self.ready(site='recovery-long', indices=[0, self.long_position, 1, 2])
        self.assertGreaterEqual(page.evaluate("compositionRuntime.nodes.get('loop-2').item.quantized.seconds"), 6.9)
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        self.wait_reattempts(page, 1)
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        gap = page.evaluate(f"{REATTEMPTS}[0].wall - compositionRuntime.events.find(e=>e.type==='handoff-deferred').wall")
        own = page.evaluate("compositionRuntime.nodes.get('loop-1').item.quantized.seconds") * 1000
        self.assertGreaterEqual(gap, own - 200)
        self.assertLess(gap, own + 2500, 'after the deferred panel\'s own loop, not the seven second sibling\'s')

    def test_paused_page_waits_without_spending_an_attempt(self):
        page = self.ready(site='settlement-variant')
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        self.pause_page(page)
        page.wait_for_timeout(7000)
        self.assertEqual(self.reattempts(page), [], 'a paused page cannot present frames; nothing is spent')
        self.resume_page(page)
        self.wait_reattempts(page, 1)
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        self.assertEqual(self.reattempts(page), [{'slots': [0], 'remaining': 1}],
                         'waiting spent no attempt: the first real attempt still has one more behind it')

    def test_hidden_page_waits_without_spending_an_attempt(self):
        page = self.ready(site='settlement-variant')
        forward = page.evaluate("compositionRuntime.nodes.get('loop-1').item.clip.id")
        page.evaluate('''() => { window.pageHidden = true;
          Object.defineProperty(document, 'hidden', {configurable: true, get: () => window.pageHidden}); }''')
        self.defer(page, 'loop-1')
        self.tap(page, '#loop-mode')
        self.wait_deferred(page)
        page.evaluate('restoreSettlementFault()')
        page.wait_for_timeout(7000)
        self.assertEqual(self.reattempts(page), [])
        page.evaluate('window.pageHidden = false')
        self.wait_reattempts(page, 1)
        page.wait_for_function(f"() => {BOOMERANG}==={forward!r}", timeout=30000)
        self.settled(page)
        self.assertEqual(self.reattempts(page), [{'slots': [0], 'remaining': 1}])

    def test_a_stale_attribution_never_schedules_a_re_attempt(self):
        """Defence in depth behind ownsIntent: a lastDeferral keyed to another
        revision must be ignored, or a sibling that failed to decode (not
        transient) would be retried as if it had been deferred."""
        page = self.ready(site='recovery-two')
        second = page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id")
        page.evaluate('''() => {
          const r=compositionRuntime, prime=r.prime.bind(r);
          window.decodeFailures=0;
          r.prime=async (...args)=>{
            if(args[1].id==='loop-2') { decodeFailures++; throw new Error('Incoming clip could not be decoded'); }
            return prime(...args);
          };
          Object.defineProperty(r,'lastDeferral',{configurable:true,
            get:()=>({revision:r.revision-1,slots:['loop-2']}),set:()=>{}});
        }''')
        self.tap(page, '#loop-mode')
        page.wait_for_function('() => decodeFailures>=1', timeout=15000)
        self.settled(page)
        page.wait_for_timeout(7000)
        self.assertEqual(page.evaluate('decodeFailures'), 1)
        self.assertEqual(self.reattempts(page), [])
        self.assertEqual(page.evaluate("compositionRuntime.nodes.get('loop-2').item.asset.id"), second)


if __name__ == '__main__':
    unittest.main()
