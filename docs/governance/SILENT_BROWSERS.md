# Silent browsers

No test or tool in this repository may produce audible sound on the host. The mute sits at the source: every
Playwright launch goes through one helper pair and a lint fails when a launch bypasses it.

- `src/simvltanea/browser/silent_browser.py` (`silent_launch`, `silent_launch_persistent_context`) and
  `src/simvltanea/browser/silent_browser.js` (`silentLaunch`, `silentLaunchPersistentContext`) launch the browser.
- Chromium gets `--mute-audio` merged into the caller's own arguments.
- Every engine gets `src/simvltanea/browser/silent_init.js` in every context (`new_context` and `new_page`). It pins
  every audio and video element to native `muted = true` and `volume = 0` (the app still reads back the values it set),
  and routes every connection to a realtime `AudioContext` destination through a per-context `GainNode` at gain 0.
  `OfflineAudioContext` keeps its real destination because it renders to a buffer, not to the device.
- An element routed into Web Audio with `createMediaElementSource` is released from the pin, because a muted element
  would feed silence to the analyser suites; its sound is silenced in the graph by the gain-0 sink.
- `speechSynthesis` utterances are spoken at volume 0.
- The helper never changes the system volume or the output device.

`test_silent_browser.py` proves the contract with silent fixtures, and `test_silent_browser_lint.py` fails on any
`chromium`, `webkit` or `firefox` launch that skips the helper. The WebKit half of the page test runs in the
macOS WebKit workflow, where a missing WebKit is a failure.

`test_silent_browser_lint.py` lives under `src/simvltanea/browser/`, so CI's `python3 -m unittest discover -s tests`
does not collect it and the named-modules step in `ci.yml` does not list it either. It is exercised only when run
directly:

```bash
PYTHONPATH=src python3 -m unittest simvltanea.browser.test_silent_browser_lint -v
```

That direct run is the check that exercises the pinned string-text and regex-literal behaviour (PR #123). Adding the
module to the named-modules list in `.github/workflows/ci.yml` is an owner-gated workflow edit (issue #71, item 1);
until that lands, the direct run is the intended gate and this page is the record of it.
