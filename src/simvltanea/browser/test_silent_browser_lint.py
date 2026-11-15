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
# Owners that are application objects, not browser types (a driver file may drive an app that has its own launch()).
SAFE_OWNERS = {'self', 'cls', 'this', 'lab', 'e', 'live', 'studio', 'player', 'runtime', 'controller', 'deck', 'app', 'window', 'document', 'console'}
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
JS_COMPUTED = re.compile(r"([\w$]+)\s*\[\s*[^\]'\"\s][^\]]*\]\s*\(")  # engine[method]()
JS_PUPPETEER = re.compile(r"\bpuppeteer\b\s*\.\s*launch|(?:require\(|from\s+)['\"]puppeteer")


def python_launches(source: str, name: str):
    """Playwright launches in Python: any ``.launch`` style call in a browser-driver file unless its owner is an app object,
    plus ``getattr(engine, 'launch')`` and an alias of an engine."""
    tree = ast.parse(source, name)
    driver = bool(DRIVER_FILE.search(source))
    aliases = set(ENGINE_NAMES if driver else PLAYWRIGHT_ENGINES)
    changed = True
    while changed:  # chained aliases: runner = bt; bt = pw.chromium
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Attribute, ast.Name)):
                label = node.value.attr if isinstance(node.value, ast.Attribute) else node.value.id
                if label in PLAYWRIGHT_ENGINES or label in aliases:
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id not in aliases:
                            aliases.add(target.id); changed = True
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr in PY_LAUNCHERS:
            owner = node.value.value  # a bound launch method kept for later: launch = pw.chromium.launch
            label = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ''
            if label in aliases or (driver and label not in SAFE_OWNERS):
                found.append(node.lineno)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == 'getattr' and len(node.args) >= 2:
            first = node.args[0]
            label = first.attr if isinstance(first, ast.Attribute) else first.id if isinstance(first, ast.Name) else ''
            second = node.args[1]
            dynamic = not (isinstance(second, ast.Constant) and isinstance(second.value, str))
            if label in aliases and (dynamic or second.value in PY_LAUNCHERS):
                found.append(node.lineno)
            continue
        if not (isinstance(func, ast.Attribute) and func.attr in PY_LAUNCHERS):
            continue
        owner = func.value
        label = owner.attr if isinstance(owner, ast.Attribute) else owner.id if isinstance(owner, ast.Name) else ''
        if label in aliases or isinstance(owner, (ast.Call, ast.Subscript)) or (driver and label not in SAFE_OWNERS):
            found.append(node.lineno)
    return sorted(found)


REGEX_AFTER = set('(,=:[!&|?{};+-*%<>~^')
REGEX_AFTER_WORDS = {'return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw', 'yield', 'await'}


def _regex_end(source: str, i: int) -> int:
    """Index just past the regex literal that opens at ``i`` (a slash), or ``i + 1`` when it does not close on its line."""
    n, j, in_class = len(source), i + 1, False
    while j < n and source[j] != '\n':
        c = source[j]
        if c == '\\':
            j += 2 if source[j + 1:j + 2] != '\n' else 1  # a backslash never carries a regex over a line break
            continue
        if c == '[':
            in_class = True
        elif c == ']':
            in_class = False
        elif c == '/' and not in_class:
            j += 1
            while j < n and (source[j].isalnum() or source[j] in '_$'):
                j += 1
            return j
        j += 1
    return i + 1


def _blank_comments(source: str) -> str:
    """Blank out comments, keeping every newline, so a commented launch is ignored and line numbers stay true.

    A small lexer, so the comment markers it blanks are real ones: string literals are walked (``" // "`` inside a
    string never hides the code after it), regex literals are skipped whole (``/\\//`` and ``/"/`` are not comments or
    strings), and template literals nest (``${ ok ? `a` : `b` }``) with their expressions lexed as code. Text inside strings,
    regexes and templates is left in place on purpose: the scan reports a launch that is only named in text (reword it)
    rather than risk hiding a real one.

    Regex versus division is guessed from the previous token, so the lexer is a guard against an accidental bare launch,
    not a parser. Known limit: a regex literal right after a closing parenthesis or brace (``if (ok) /\\//.test(s)``) is read as
    division, and a ``//`` or ``/*`` inside it is then read as a comment, which can hide a launch later on that line."""
    out, i, n = [], 0, len(source)
    frames = [['code', 0]]  # [kind, open-brace depth]; a template literal pushes 'tmpl', a ${ pushes 'code'
    prev, prev_word = '', ''
    while i < n:
        kind, c, pair = frames[-1][0], source[i], source[i:i + 2]
        if kind == 'tmpl':
            if c == '\\' and i + 1 < n:
                out.append(source[i:i + 2]); i += 2
            elif c == '`':
                frames.pop(); out.append(c); i += 1; prev = '`'; prev_word = ''
            elif pair == '${':
                frames.append(['code', 0]); out.append(pair); i += 2; prev = '{'
            else:
                out.append(c); i += 1
            continue
        if pair == '//':
            j = source.find('\n', i)
            j = n if j < 0 else j
            out.append(' ' * (j - i)); i = j
            continue
        if pair == '/*':
            j = source.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r'[^\n]', ' ', source[i:j])); i = j
            continue
        if c in '"\'':
            j = i + 1
            while j < n and source[j] != c and source[j] != '\n':
                j += 2 if source[j] == '\\' else 1
            j = min(j + 1, n)
            out.append(source[i:j]); i = j; prev = c; prev_word = ''
            continue
        if c == '`':
            frames.append(['tmpl', 0]); out.append(c); i += 1
            continue
        if c == '/' and (prev == '' or prev in REGEX_AFTER or prev_word in REGEX_AFTER_WORDS) and not re.search(
                r'(\+\+|--)\s*$', source[max(0, i - 64):i]):
            j = _regex_end(source, i)
            out.append(source[i:j]); i = j; prev = ')'; prev_word = ''
            continue
        if c == '{':
            frames[-1][1] += 1
        elif c == '}':
            if frames[-1][1] == 0 and len(frames) > 1:
                frames.pop(); out.append(c); i += 1; prev = ')'; prev_word = ''
                continue
            frames[-1][1] = max(0, frames[-1][1] - 1)
        out.append(c); i += 1
        if not c.isspace():
            if c.isalnum() or c in '_$':
                before = source[i - 2] if i >= 2 else ''
                # a word continues only when the character right before it is a word character; a member name is not a keyword
                prev_word = prev_word + c if before.isalnum() or before in ('_', '$') else ('.' + c if before == '.' else c)
            else:
                prev_word = ''
            prev = c
    return ''.join(out)


def node_launches(source: str):
    code = _blank_comments(source)
    driver = bool(DRIVER_FILE.search(code))
    names = set(ENGINE_NAMES if driver else PLAYWRIGHT_ENGINES)
    changed = True
    while changed:  # chained aliases: const bt = playwright.webkit; const runner = bt;
        before = len(names)
        pattern = re.compile(r"([\w$]+)\s*=\s*(?:[\w$.()'\"\[\]]*?\.)?(?:" + "|".join(sorted(re.escape(n) for n in names)) + r")\b(?!\s*\.\s*launch)")
        names |= {m.group(1) for m in pattern.finditer(code)}
        changed = len(names) != before
    names |= {m.group(1) for m in JS_ALIAS_DESTRUCTURE.finditer(code)} | {m.group(1) for m in JS_ALIAS_IMPORT.finditer(code)}
    found = set()
    for match in JS_CALL.finditer(code):
        owner = match.group('owner') or match.group('owner2')
        tail = re.search(r"([\w$]+)$", owner)
        tail_name = tail.group(1) if tail else ''
        if (driver and owner.endswith(']')) or tail_name in names or (driver and tail_name not in SAFE_OWNERS):
            found.add(code.count('\n', 0, match.start() + len(match.group(0)) - len(re.search(rf"(?:{NAMES})\b.*$", match.group(0), re.S).group(0))) + 1)
    for match in JS_COMPUTED.finditer(code):  # chromium[method]()
        if match.group(1) in names:
            found.add(code.count('\n', 0, match.start()) + 1)
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
        self.assertEqual(node_launches("const bt = playwright.webkit; const runner = bt; await runner.launch();\n"), [1])
        self.assertEqual(node_launches("const method = 'launch'; await chromium[method]();\n"), [1])
        self.assertEqual(node_launches("const pw = require('playwright'); await thing.launch();\n"), [1])
        self.assertEqual(python_launches("import playwright\nlaunch = getattr(pw.chromium, 'launch')\n", 'x.py'), [2])
        self.assertEqual(python_launches("import playwright\nbt = pw.chromium\nrunner = bt\nrunner.launch()\n", 'x.py'), [4])
        self.assertEqual(python_launches("import playwright\nlaunch = pw.chromium.launch\nlaunch()\n", 'x.py'), [2])
        self.assertEqual(node_launches('/* webkit.launch() */ const x = 1;\n'), [])
        self.assertEqual(node_launches('const note = " // "; webkit.launch();\n'), [1])
        # Text that only names a launch is reported (reword it): string text is never blanked, so a lexer slip cannot hide a launch.
        self.assertEqual(node_launches('const note = "webkit.launch()";\n'), [1])
        # Regex literals are lexed whole: a quote, a slash pair or a block-comment opener inside one is not code structure.
        self.assertEqual(node_launches('s.replace(/"/g, ""); await webkit.launch();\n'), [1])
        self.assertEqual(node_launches('if (/"/.test(a)) f("x // y"); await webkit.launch();\n'), [1])
        self.assertEqual(node_launches('s.replace(/"/g, ""); u = "a // b"; webkit.launch();\n'), [1])
        self.assertEqual(node_launches('const parts = p.split(/\\//); await chromium.launch();\n'), [1])
        self.assertEqual(node_launches('const g = /a\\/*/; await webkit.launch(); /* real comment */\n'), [1])
        self.assertEqual(node_launches("s.replace(/`/g, '');\nawait webkit.launch();\nconst t = `x`;\n"), [2])
        self.assertEqual(node_launches('return /x/.test(y); // webkit.launch()\n'), [])
        self.assertEqual(node_launches('const r = a / b; // webkit.launch()\n'), [])
        # Template literals nest and their expressions are code.
        self.assertEqual(node_launches('const s = `${ok ? `a` : `b`}`;\nfetch("http://x"); webkit.launch();\n'), [2])
        self.assertEqual(node_launches('x = `a ${ {b: 1}.b } c`; // webkit.launch()\nwebkit.launch();\n'), [2])
        # Known limit (see _blank_comments): a regex right after a closing parenthesis is read as division.
        self.assertEqual(node_launches('if (ok) /\\//.test(s); await webkit.launch();\n'), [])
        # Division is not a regex: after a postfix operator, a string, a template and a closed expression.
        self.assertEqual(node_launches('x = `${ i++ / 2 } a ${ j / 3 }`; // webkit.launch()\nwebkit.launch();\n'), [2])
        self.assertEqual(node_launches('return "a" / 2; // webkit.launch()\nwebkit.launch();\n'), [2])
        self.assertEqual(node_launches('x = i++        / 2; // webkit.launch()\nwebkit.launch();\n'), [2])
        self.assertEqual(node_launches('const half = cfg.of / 2; const u = "a"; // webkit.launch()\nwebkit.launch();\n'), [2])
        self.assertEqual(node_launches('else return /"/.test(s); await webkit.launch();\n'), [1])
        self.assertEqual(node_launches('x = `x` / 2; // webkit.launch()\nwebkit.launch();\n'), [2])
        self.assertEqual(node_launches('x = /a\\\n/; // webkit.launch()\nwebkit.launch();\n'), [3])
        self.assertEqual(node_launches('const s = "a\\" // b"; await webkit.launch();\n'), [1])
        self.assertEqual(node_launches('const url = "http://x"; // chromium.launch()\n'), [])
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
