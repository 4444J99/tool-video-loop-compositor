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
LAUNCHERS = {'launch', 'launch_persistent_context', 'launch_server', 'connect', 'connect_over_cdp',
             'launchPersistentContext', 'launchServer', 'connectOverCDP'}
ENGINES = {'chromium', 'webkit', 'firefox', '_electron', 'electron', 'android'}
# A Node launch is ``<engine>.launch(`` where the engine is a Playwright browser type, however it was named:
# ``chromium``, ``webkit``, ``playwright.webkit``, or a parameter such as ``browserType`` or ``engine``.
JS_LAUNCH = re.compile(r'(?<![\w$])(?P<owner>[\w$.]*?)\b(?P<call>launch|launchPersistentContext|launchServer|connectOverCDP)\s*\(')
JS_OWNERS = re.compile(r'(?:^|\.)(?:chromium|webkit|firefox|electron|browserType|browser_type|engine)$')
SELF_LAUNCH = re.compile(r'\b(?:engine|lab|e|live|studio|this|self|player|runtime|controller|deck)$')


def scanned(suffixes):
    for top in SCANNED:
        base = ROOT / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            relative = path.relative_to(ROOT).as_posix()
            if path.suffix in suffixes and path.is_file() and relative not in EXEMPT and 'node_modules' not in path.parts:
                yield path, relative


def python_launches(source: str, name: str):
    """Calls ``<x>.chromium.launch(...)``, ``<x>.webkit.launch_persistent_context(...)`` and the other engines."""
    found = []
    for node in ast.walk(ast.parse(source, name)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LAUNCHERS):
            continue
        owner = node.func.value
        label = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ''
        if label in ENGINES or label in {'browser_type', 'engine'}:
            found.append(node.lineno)
    return found


def node_launches(source: str):
    found = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(('//', '*', '/*')):
            continue
        for match in JS_LAUNCH.finditer(line):
            owner = match.group('owner').rstrip('.')
            if owner and JS_OWNERS.search(owner) and not SELF_LAUNCH.search(owner):
                found.append(number)
    return found


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
