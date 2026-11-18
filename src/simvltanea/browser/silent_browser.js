/* Launch every Playwright browser through here so no run can make a sound. Node twin of silent_browser.py: same
 * rule, same silent_init.js. Chromium gets --mute-audio merged into the caller's arguments, and every context
 * (newContext, and newPage, which makes its own) gets the init script that pins media muted at volume 0 and puts
 * a gain-0 sink in front of every realtime AudioContext destination. Firefox has no mute flag and none can be
 * injected: Playwright cannot set the float pref media.volume_scale through firefoxUserPrefs — a number breaks
 * every Firefox launch (juggler calls setIntPref for any number, the pref is a float, NS_ERROR_UNEXPECTED;
 * verified live at Playwright 1.57.0 / Firefox 144.0.2 in simvltanea #124, and the same signature at 1.62.1 /
 * Firefox 153 in timed-text #89) and a string is stored as a string and ignored by the float getter. Caller
 * prefs are forwarded unchanged and no engine pref is injected; Firefox relies on the init script alone.
 * WebKit cannot be muted at the engine either, and the init script cannot reach media parsed inside a closed
 * declarative shadow root, so such a page is refused before any browser launches: call
 * assertNoClosedShadowRoots on a check page's HTML and the run fails loudly, naming the page. */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const INIT_SCRIPT_PATH = path.join(__dirname, 'silent_init.js');
const MUTE_ARGS = ['--mute-audio'];
const initScript = () => fs.readFileSync(INIT_SCRIPT_PATH, 'utf8');

// A closed declarative shadow root (<template shadowrootmode="closed">, quoting and whitespace variants, any case)
// hides media no page script can reach. The init script cannot pin it, so the page is refused at pre-flight
// instead of going audible.
const CLOSED_SHADOW_ROOT_RE = /shadowrootmode\s*=\s*(?:"closed"|'closed'|closed(?=[\s/>]))/i;

function assertNoClosedShadowRoots(html, source = 'page') {
  if (CLOSED_SHADOW_ROOT_RE.test(html || '')) {
    throw new Error(`${source}: closed declarative shadow root (shadowrootmode="closed") — ` +
      'media inside it cannot be pinned, refusing the page');
  }
}

const engineName = engine => (typeof engine.name === 'function' ? engine.name() : engine.name);

function silentArgs(name, args = []) {
  const merged = [...args];
  if (name === 'chromium') for (const flag of MUTE_ARGS) if (!merged.includes(flag)) merged.push(flag);
  return merged;
}

async function silenceContext(context) {
  await context.addInitScript({path: INIT_SCRIPT_PATH});
  return context;
}

function silenceBrowser(browser) {
  if (browser.__silentBrowser) return browser;
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => silenceContext(await newContext(...args));
  // Playwright's own newPage makes a context after the fact, so a script added to it would miss the blank document
  // that setContent and addScriptTag write into. Make the silenced context first, then the page, and close the
  // context with the page the way Playwright's owned context does.
  browser.newPage = async (...args) => {
    const context = await browser.newContext(...args), page = await context.newPage(), pageClose = page.close.bind(page);
    page.close = async (...closeArgs) => { try { await pageClose(...closeArgs); } finally { await context.close(); } };
    return page;
  };
  browser.__silentBrowser = true;
  return browser;
}

async function silentLaunch(engine, options = {}) {
  const name = engineName(engine);
  const launchOptions = {...options, args: silentArgs(name, options.args)};
  // No engine pref is injected for Firefox: Playwright cannot set the float pref media.volume_scale
  // (see the header); caller firefoxUserPrefs pass through unchanged.
  return silenceBrowser(await engine.launch(launchOptions));
}

// A persistent context is created with its first page already open, so that page's document is silenced by running
// the init script in it now; every later document and navigation gets it from the context.
async function silentLaunchPersistentContext(engine, userDataDir, options = {}) {
  const name = engineName(engine);
  const launchOptions = {...options, args: silentArgs(name, options.args)};
  const context = await silenceContext(await engine.launchPersistentContext(userDataDir, launchOptions));
  for (const page of context.pages()) await page.evaluate(initScript());
  return context;
}

module.exports = {INIT_SCRIPT_PATH, MUTE_ARGS, CLOSED_SHADOW_ROOT_RE, assertNoClosedShadowRoots, initScript, silentArgs, silenceContext, silenceBrowser, silentLaunch, silentLaunchPersistentContext};
