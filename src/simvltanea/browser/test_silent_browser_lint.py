"""Fail when a test or tool launches a browser without going through the silent helper.

The silence rule is absolute (no run may produce audible sound), so there is no ratchet: every launch in ``src``,
``tools`` and ``tests`` is ``silent_launch`` (Python) or ``silentLaunch`` (Node). The helper modules and this lint are
the only files that may call the Playwright launch API itself. Archived sources are history, never run.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCANNED = ('src', 'tools', 'tests')
EXEMPT = {'src/simvltanea/browser/silent_browser.py', 'src/simvltanea/browser/silent_browser.js',
          'src/simvltanea/browser/test_silent_browser.py', 'src/simvltanea/browser/test_silent_browser_lint.py'}
def scanned(suffixes):
    for top in SCANNED:
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix in suffixes and path.is_file() and relative not in EXEMPT and 'node_modules' not in path.parts:
                yield path, relative


ENGINE_NAMES = {'chromium', 'webkit', 'firefox', '_electron', 'electron', 'browserType', 'browser_type', 'engine'}
PLAYWRIGHT_ENGINES = {'chromium', 'webkit', 'firefox'}
PY_LAUNCHERS = {'launch', 'launch_persistent_context', 'launch_server', 'connect_over_cdp'}
NAMES = 'launch|launchPersistentContext|launchServer|connectOverCDP'
# obj.launch(, obj\n  .launch(, obj['launch'](, and a launch pulled out by destructuring or bound for later.
JS_CALL = re.compile(rf"(?P<owner>[\w$.\]\[]*?[\w$\]])\s*\.\s*(?:{NAMES})\b|(?P<owner2>[\w$]+)\s*\[\s*['\"](?:{NAMES})['\"]\s*\]")
JS_DESTRUCTURED = re.compile(rf"\{{[^}}]*\b(?:{NAMES})\b[^}}]*\}}\s*=\s*[\w$.\]\[]*?(?:chromium|webkit|firefox|browserType|engine)\b")
# A Playwright engine under another name: const runner = chromium; const {chromium: runner} = require('playwright');
JS_ALIAS_ASSIGN = re.compile(r"([\w$]+)\s*=\s*(?:[\w$.()'\"\[\]]*?\.)?(?:chromium|webkit|firefox)\b(?!\s*\.\s*launch)")
JS_ALIAS_DESTRUCTURE = re.compile(r"\b(?:chromium|webkit|firefox)\s*:\s*([\w$]+)")
JS_ALIAS_IMPORT = re.compile(r"\b(?:chromium|webkit|firefox)\s+as\s+([\w$]+)")  # import {chromium as chrome} from 'playwright'
# Names such as ``engine`` are Playwright browser types only in a file that deals with a browser driver; application code
# has its own ``engine.launch(...)``.
DRIVER_FILE = re.compile(r"playwright|puppeteer|chromium|firefox|browserType|browser_type|\bwebkit\s*[.,)]", re.I)
JS_PUPPETEER = re.compile(r"\bpuppeteer\b\s*\.\s*launch|(?:require\(|from\s+)['\"]puppeteer")


def python_launches(source: str, name: str):
    """Playwright launches in Python: ``p.chromium.launch()``, an alias of an engine, ``getattr(p, name).launch()``."""
    tree = ast.parse(source, name)
    aliases = set(ENGINE_NAMES if DRIVER_FILE.search(source) else PLAYWRIGHT_ENGINES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Attribute, ast.Name)):
            label = node.value.attr if isinstance(node.value, ast.Attribute) else node.value.id
            if label in PLAYWRIGHT_ENGINES:
                aliases.update(target.id for target in node.targets if isinstance(target, ast.Name))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in PY_LAUNCHERS):
            continue
        owner = node.func.value
        label = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ''
        if label in aliases or isinstance(owner, (ast.Call, ast.Subscript)):
            found.append(node.lineno)
    return sorted(found)


def _blank_comments(source: str) -> str:
    """Blank out comments but keep every newline, so a commented launch is ignored and line numbers stay true."""
    source = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), source, flags=re.S)
    return re.sub(r"(?m)(^|[^:'\"`])//[^\n]*", lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), source)


def node_launches(source: str):
    code = _blank_comments(source)
    driver = bool(DRIVER_FILE.search(code))
    names = set(ENGINE_NAMES if driver else PLAYWRIGHT_ENGINES) | {m.group(1) for m in JS_ALIAS_ASSIGN.finditer(code)} | {m.group(1) for m in JS_ALIAS_DESTRUCTURE.finditer(code)} | {m.group(1) for m in JS_ALIAS_IMPORT.finditer(code)}
    found = set()
    for match in JS_CALL.finditer(code):
        owner = match.group('owner') or match.group('owner2')
        tail = re.search(r"([\w$]+)$", owner)
        if (driver and owner.endswith(']')) or (tail and tail.group(1) in names):
            found.add(code.count('\n', 0, match.start() + len(match.group(0)) - len(re.search(rf"(?:{NAMES})\b.*$", match.group(0), re.S).group(0))) + 1)
    for match in (JS_DESTRUCTURED.finditer(code) if driver else []):
        found.add(code.count('\n', 0, match.start()) + 1)
    puppeteer = JS_PUPPETEER.search(code)
    if puppeteer:
        found.add(code.count('\n', 0, puppeteer.start()) + 1)
    return sorted(found)


class SilentLaunchLintTests(unittest.TestCase):
    def test_no_python_file_launches_a_browser_around_the_helper(self):
        bare = [f'{relative}:{line}' for path, relative in scanned({'.py'})
                for line in python_launches(path.read_text(encoding='utf-8'), relative)]
        self.assertEqual(bare, [], 'launch through simvltanea.browser.silent_browser.silent_launch so the run is silent')

    def test_no_node_file_launches_a_browser_around_the_helper(self):
        bare = [f'{relative}:{line}' for path, relative in scanned({'.js', '.mjs', '.cjs'})
                for line in node_launches(path.read_text(encoding='utf-8'))]
        self.assertEqual(bare, [], 'launch through silent_browser.js silentLaunch so the run is silent')

    def test_the_lint_sees_a_bare_launch_and_accepts_the_helper(self):
        self.assertEqual(python_launches('runner = pw.chromium\nrunner.launch()\n', 'x.py'), [2])
        self.assertEqual(python_launches('getattr(pw, name).launch()\n', 'x.py'), [1])
        self.assertEqual(node_launches('await chromium\n  .launch({headless:true});\n'), [2])
        self.assertEqual(node_launches('const runner = chromium;\nawait runner.launch();\n'), [2])
        self.assertEqual(node_launches("const {chromium: runner} = require('playwright');\nawait runner.launch();\n"), [2])
        self.assertEqual(node_launches("await playwright[kind].launch();\n"), [1])
        self.assertEqual(node_launches("await chromium['launch']();\n"), [1])
        self.assertEqual(node_launches("const {launch} = chromium;\nawait launch();\n"), [1])
        self.assertEqual(node_launches("import { chromium as chrome } from 'playwright';\nawait chrome.launch();\n"), [2])
        self.assertEqual(node_launches('/* webkit.launch() */ const x = 1;\n'), [])
        self.assertEqual(node_launches('await engine.launch(id);\n'), [])
        self.assertEqual(python_launches('pw.chromium.launch(headless=True)\n', 'x.py'), [1])
        self.assertEqual(python_launches('cls.pw.webkit.launch_persistent_context("/p")\n', 'x.py'), [1])
        self.assertEqual(python_launches('playwright.firefox.connect_over_cdp("ws://x")\n', 'x.py'), [1])
        self.assertEqual(python_launches('silent_launch(pw.chromium, headless=True)\n', 'x.py'), [])
        self.assertEqual(python_launches('lab.launch(layer)\n', 'x.py'), [])
        self.assertEqual(node_launches('browser = await webkit.launch({headless: true});\n'), [1])
        self.assertEqual(node_launches('const b = await playwright.chromium.launch();\n'), [1])
        self.assertEqual(node_launches('await browserType.launchPersistentContext(dir, {});\n'), [1])
        self.assertEqual(node_launches('browser = await silentLaunch(webkit, {headless: true});\n'), [])
        self.assertEqual(node_launches('await engine.launch(id);\n'), [])
        self.assertEqual(node_launches('// webkit.launch({headless: true})\n'), [])

    def test_the_helper_pair_is_the_only_launcher(self):
        helper = (ROOT / 'src/simvltanea/browser/silent_browser.py').read_text(encoding='utf-8')
        self.assertEqual(len(python_launches(helper, 'silent_browser.py')), 2)


if __name__ == '__main__':
    unittest.main()
