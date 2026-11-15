'use strict';
// Non-gating discrimination of "the page stalled" from "the host observer stalled" (issue 115).
//
// The verifiers sample the page with page.evaluate. A gap between two samples can come from the page (its main
// thread or decoders stopped) or from the runner (the observer's event loop or the driver pipe was delayed while the
// page kept running). Hosted-run artifacts showed both shapes: a 2.07 s gap during which the page's own frame
// callbacks and simulation clock kept advancing, and a 4.3 to 9.7 s window in which every deck's frame callbacks and
// decoded-frame counters stood still while the sampler stayed responsive. These helpers record the facts that separate
// them. They never change a verdict; they make a red run attributable from its receipt alone.

const os = require('node:os');

const GAP_MS = 1000;
const FREEZE_MS = 1500;

// Runner-side stamps around one page.evaluate. Both clocks are Date.now() on the same host, so the row's own epochMs
// (taken inside the page when the sample ran) splits the round trip into dispatch and return latency.
// The monitor timer measures how late this process's own event loop runs, independent of the page. A late loop means
// the runner was busy or starved (the host side of a gap); an on-time loop beside a stalled page points at the page.
const MONITOR_MS = 50;
let monitor = null, lastTick = 0, maxLagMs = 0;
function startMonitor() {
  if (monitor) return;
  lastTick = Date.now();
  monitor = setInterval(() => {
    const now = Date.now();
    maxLagMs = Math.max(maxLagMs, now - lastTick - MONITOR_MS);
    lastTick = now;
  }, MONITOR_MS);
  monitor.unref();
}

async function observe(page, fn, arg) {
  startMonitor();
  const sentAtMs = Date.now();
  const row = await page.evaluate(fn, arg);
  if (row && typeof row === 'object') {
    // Date.now() here, not the monitor's last tick: a blocked loop has not ticked, so the lag so far is the larger of
    // the recorded maximum and the time since the last tick.
    const returnedAtMs = Date.now(), eventLoopLagMs = Math.max(maxLagMs, returnedAtMs - lastTick - MONITOR_MS, 0);
    maxLagMs = 0;
    row.runner = {sentAtMs, returnedAtMs, eventLoopLagMs, loadAvg1: Number(os.loadavg()[0].toFixed(2))};
  }
  return row;
}

const callbackTotal = row => (row.decks || []).reduce((sum, deck) => sum + (Number.isFinite(deck.callbacks) ? deck.callbacks : 0), 0);
const frameTotal = row => (row.decks || []).reduce((sum, deck) =>
  sum + (Number.isFinite(deck.quality?.totalVideoFrames) ? deck.quality.totalVideoFrames : 0), 0);

// True when, between two samples, the page's simulation clock advanced at least 90% of the wall gap and the named deck
// (matched by id and deck index) kept receiving frame callbacks. The delay was then in the observer, not the page.
function pageAliveAcross(before, after, identity) {
  const gapMs = after.wall - before.wall;
  if (!(gapMs > 0) || !Number.isFinite(after.simTime) || !Number.isFinite(before.simTime)) return false;
  const find = row => (row.decks || []).find(deck => deck.populated && deck.id === identity.id && deck.deck === identity.deck);
  const was = find(before), now = find(after);
  return (after.simTime - before.simTime) * 1000 >= gapMs * .9 && Boolean(was && now) &&
    Number.isFinite(was.callbacks) && Number.isFinite(now.callbacks) && now.callbacks > was.callbacks;
}

// Gaps longer than GAP_MS between consecutive samples. pageAlive is true when, across the gap, the page's simulation
// clock advanced and its frame callbacks kept arriving: the delay was then in the observer, not in the page.
function samplerGaps(rows, thresholdMs = GAP_MS) {
  const gaps = [];
  for (let index = 1; index < (rows || []).length; index++) {
    const before = rows[index - 1], after = rows[index], gapMs = after.wall - before.wall;
    if (!(gapMs > thresholdMs)) continue;
    const runner = after.runner, simAdvancedMs = Number.isFinite(after.simTime) && Number.isFinite(before.simTime)
      ? Math.round((after.simTime - before.simTime) * 1000) : null;
    const callbackDelta = callbackTotal(after) - callbackTotal(before);
    gaps.push({fromWall: before.wall, toWall: after.wall, gapMs: Math.round(gapMs),
      dispatchMs: runner && Number.isFinite(after.epochMs) ? after.epochMs - runner.sentAtMs : null,
      returnMs: runner && Number.isFinite(after.epochMs) ? runner.returnedAtMs - after.epochMs : null,
      eventLoopLagMs: runner?.eventLoopLagMs ?? null, loadAvg1: runner?.loadAvg1 ?? null,
      simAdvancedMs, callbackDelta, pageAlive: simAdvancedMs !== null && simAdvancedMs >= gapMs * .9 && callbackDelta > 0});
  }
  return {thresholdMs, count: gaps.length, maxGapMs: gaps.reduce((max, gap) => Math.max(max, gap.gapMs), 0),
    pageAliveCount: gaps.filter(gap => gap.pageAlive).length, gaps: gaps.slice(0, 16)};
}

// Windows of at least FREEZE_MS in which every populated, unpaused, ready deck made no frame-callback and no
// decoded-frame progress while samples kept arriving. seekingDecks and wrapsAtOnset say whether the window started
// next to a native loop seek, the one product action that could plausibly provoke a whole-page decoder stall.
function decodeFreezes(rows, thresholdMs = FREEZE_MS) {
  const windows = [];
  let run = null;
  // The duration is a lower bound: from the first to the last sample that showed the same counters.
  const close = () => {
    if (run && run.lastWall - run.firstWall >= thresholdMs) {
      windows.push({fromWall: run.firstWall, toWall: run.lastWall, durationMs: Math.round(run.lastWall - run.firstWall),
        samples: run.samples, seekingDecksAtOnset: run.seeking,
        maxEventLoopLagMs: run.lagMs, maxLoadAvg1: run.load, simAdvancedMs: Math.round((run.lastSim - run.firstSim) * 1000)});
    }
    run = null;
  };
  for (const row of rows || []) {
    const running = (row.decks || []).filter(deck => deck.populated && !deck.paused && deck.ready >= 3);
    if (!running.length) { close(); continue; }
    const key = callbackTotal(row) + ':' + frameTotal(row);
    if (run && run.key === key) {
      run.lastWall = row.wall; run.lastSim = row.simTime; run.samples++;
      if (row.runner) {
        run.lagMs = Math.max(run.lagMs ?? 0, row.runner.eventLoopLagMs ?? 0); run.load = Math.max(run.load ?? 0, row.runner.loadAvg1 ?? 0);
      }
    } else {
      close();
      run = {key, firstWall: row.wall, lastWall: row.wall, firstSim: row.simTime, lastSim: row.simTime, samples: 1, lagMs: row.runner?.eventLoopLagMs ?? null, load: row.runner?.loadAvg1 ?? null,
        seeking: (row.decks || []).filter(deck => deck.populated && deck.seeking).length};
    }
  }
  close();
  return {thresholdMs, count: windows.length, longestMs: windows.reduce((max, window) => Math.max(max, window.durationMs), 0),
    windows: windows.slice(0, 16)};
}

module.exports = {pageAliveAcross, observe, samplerGaps, decodeFreezes, GAP_MS, FREEZE_MS};
