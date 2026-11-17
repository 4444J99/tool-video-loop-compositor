/* Launch every Playwright browser through here so no run can make a sound. Node twin of silent_browser.py: same
 * rule, same silent_init.js. Chromium gets --mute-audio merged into the caller's arguments, and every context
 * (newContext, and newPage, which makes its own) gets the init script that pins media muted at volume 0 and puts
 * a gain-0 sink in front of every realtime AudioContext destination. */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const INIT_SCRIPT_PATH = path.join(__dirname, 'silent_init.js');
const MUTE_ARGS = ['--mute-audio'];
const FIREFOX_PREFS = {'media.volume_scale': 0.0};
const initScript = () => fs.readFileSync(INIT_SCRIPT_PATH, 'utf8');

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
  if (name === 'firefox') {
    launchOptions.firefoxUserPrefs = {...(options.firefoxUserPrefs || {}), ...FIREFOX_PREFS};
    // keep caller prefs authoritative where already set
    for (const key of Object.keys(options.firefoxUserPrefs || {})) launchOptions.firefoxUserPrefs[key] = options.firefoxUserPrefs[key];
  }
  return silenceBrowser(await engine.launch(launchOptions));
}

// A persistent context is created with its first page already open, so that page's document is silenced by running
// the init script in it now; every later document and navigation gets it from the context.
async function silentLaunchPersistentContext(engine, userDataDir, options = {}) {
  const name = engineName(engine);
  const launchOptions = {...options, args: silentArgs(name, options.args)};
  if (name === 'firefox') {
    launchOptions.firefoxUserPrefs = {...(options.firefoxUserPrefs || {}), ...FIREFOX_PREFS};
    for (const key of Object.keys(options.firefoxUserPrefs || {})) launchOptions.firefoxUserPrefs[key] = options.firefoxUserPrefs[key];
  }
  const context = await silenceContext(await engine.launchPersistentContext(userDataDir, launchOptions));
  for (const page of context.pages()) await page.evaluate(initScript());
  return context;
}

module.exports = {INIT_SCRIPT_PATH, MUTE_ARGS, FIREFOX_PREFS, initScript, silentArgs, silenceContext, silenceBrowser, silentLaunch, silentLaunchPersistentContext};
