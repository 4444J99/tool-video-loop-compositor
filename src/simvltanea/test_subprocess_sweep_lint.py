"""Fail when a test spawns a render, ffmpeg or node child through a bare subprocess call.

A child killed by an outside SIGTERM says nothing about the code under test, so every test that spawns one
goes through ``simvltanea.subprocess_retry.run``. The sender of that signal is unconfirmed (see
``docs/governance/TEST_CHILD_PROCESSES.md``), which is why the retry sits at each call site and not in a fixture.

``PENDING`` is the ratchet for call sites not converted yet: a file listed there may still hold bare calls, a file
not listed may not, and a listed file that no longer holds any must be removed from the list.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = ('src', 'tools', 'tests')
EXEMPT = {'src/simvltanea/subprocess_retry.py', 'src/simvltanea/test_subprocess_retry.py',
          'src/simvltanea/test_subprocess_sweep_lint.py'}
BARE = {'run', 'check_output', 'check_call', 'call', 'Popen'}
# What marks a child as a render, ffmpeg or node child: the program, or a name that stands for it. A python
# ``-m`` module child (the CLI, a build or a verifier) can render as well, so it counts too.
CHILD = re.compile(r'ffmpeg|ffprobe|\bnode\b|\bNODE\b|node_executable|render', re.IGNORECASE)
# Programs that are never a render, ffmpeg or node child, whatever their arguments say (a commit message may say render).
OTHER_PROGRAMS = {'git', 'swift', 'rm'}
PYTHON = re.compile(r'executable|python')
MODULE = re.compile(r"['\"]-m['\"]")

PENDING: set[str] = {
    'tools/editions/test_inaugural_fixture.py',
    'tools/media/test_build_boomerangs.py',
    'tools/media/test_build_lab_dataset.py',
    'tools/media/test_build_public_demo.py',
    'tools/media/test_fetch_speech_model.py',
    'tools/media/test_index_clips.py',
    'tools/media/test_play_state.py',
    'tools/media/test_screen_audio.py',
    'tools/media/test_tag_clips.py',
    'tools/media/test_video_geometry.py',
    'tools/verification/test_archive_media_provenance.py',
    'tools/verification/test_build_studio_site.py',
    'tools/verification/test_cli_doctor.py',
    'tools/verification/test_functional_identity.py',
    'tools/verification/test_iteration_replays.py',
    'tools/verification/test_review_proof.py',
    'tools/verification/test_stage_library_site.py',
}


def is_test_file(path: Path) -> bool:
    name = path.name
    return name.startswith('test_') or name == 'conftest.py' or name.startswith('e2e_') or 'tests' in path.relative_to(ROOT).parts


def opaque(command: ast.AST) -> bool:
    if isinstance(command, ast.Name):
        return True
    return isinstance(command, ast.List) and any(isinstance(item, ast.Starred) for item in command.elts)


def assigned(tree: ast.AST, names: set[str]) -> list[ast.AST]:
    """Every value the module assigns to one of ``names``, plain or annotated, at any depth."""
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
            values.append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None \
                and isinstance(node.target, ast.Name) and node.target.id in names:
            values.append(node.value)
    return values


def program_of(command: ast.AST, tree: ast.AST) -> str | None:
    """The program a command list starts with, following a name or an unpacked name to what it was assigned."""
    if isinstance(command, ast.List) and command.elts:
        head = command.elts[0]
        if isinstance(head, ast.Starred):
            head = head.value
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
        if isinstance(head, ast.Name):
            for value in assigned(tree, {head.id}):
                found = program_of(value, tree)
                if found:
                    return found
    if isinstance(command, ast.Name):
        for value in assigned(tree, {command.id}):
            found = program_of(value, tree)
            if found:
                return found
    return None


def bare_child_calls(source: str) -> list[int]:
    """Line numbers of subprocess calls that spawn a render, ffmpeg or node child without the retry helper."""
    tree = ast.parse(source)
    modules, functions = {'subprocess'}, set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.asname for alias in node.names if alias.name == 'subprocess' and alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module == 'subprocess':
            functions.update(alias.asname or alias.name for alias in node.names if alias.name in BARE)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        through_module = isinstance(func, ast.Attribute) and func.attr in BARE \
            and isinstance(func.value, ast.Name) and func.value.id in modules
        through_import = isinstance(func, ast.Name) and func.id in functions
        if not (through_module or through_import):
            continue
        if node.args and program_of(node.args[0], tree) in OTHER_PROGRAMS:
            continue
        text = ast.unparse(node)
        if node.args and opaque(node.args[0]):
            # An opaque command (a variable, or a list that unpacks one): add what its names were assigned anywhere in
            # the module, so a module-level command used inside a function is seen as well.
            names = {n.id for n in ast.walk(node.args[0]) if isinstance(n, ast.Name)}
            text += ' ' + ' '.join(ast.unparse(value) for value in assigned(tree, names))
        if CHILD.search(text) or (PYTHON.search(text) and MODULE.search(text)):
            lines.append(node.lineno)
    return sorted(lines)


def scan() -> dict[str, list[int]]:
    found = {}
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob('*.py')):
            relative = path.relative_to(ROOT).as_posix()
            if relative in EXEMPT or not is_test_file(path):
                continue
            lines = bare_child_calls(path.read_text(encoding='utf-8'))
            if lines:
                found[relative] = lines
    return found


class DetectorTests(unittest.TestCase):
    def test_flags_bare_ffmpeg_node_and_render_children(self):
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['ffmpeg', '-i', 'x'])\n"), [2])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.check_output(['ffprobe', 'x'])\n"), [2])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['node', '-e', 's'])\n"), [2])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.Popen([NODE, '-e', 's'])\n"), [2])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run([sys.executable, '-m', 'pkg.render'])\n"), [2])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run([sys.executable, '-m', 'pkg.cli'])\n"), [2])

    def test_judges_an_opaque_command_by_what_it_was_assigned(self):
        source = "import subprocess\ndef go():\n    command = ['ffmpeg', 'x']\n    subprocess.run(command)\n"
        self.assertEqual(bare_child_calls(source), [4])
        starred = "import subprocess\ndef go():\n    common = ['ffmpeg', '-y']\n    subprocess.run([*common, 'x'])\n"
        self.assertEqual(bare_child_calls(starred), [4])
        self.assertEqual(bare_child_calls("import subprocess\ndef go():\n    command = ['git', 'x']\n    subprocess.run(command)\n"), [])

    def test_follows_annotated_and_module_level_commands(self):
        annotated = "import subprocess\ndef go():\n    command: list = ['ffmpeg', 'x']\n    subprocess.run(command)\n"
        self.assertEqual(bare_child_calls(annotated), [4])
        module_level = "import subprocess\nCOMMAND = ['node', '-e', '0']\ndef go():\n    subprocess.run(COMMAND)\n"
        self.assertEqual(bare_child_calls(module_level), [4])
        unpacked = "import subprocess\nCOMMON = ['ffmpeg', '-y']\nclass T:\n    def go(self):\n        subprocess.run([*COMMON, 'x'])\n"
        self.assertEqual(bare_child_calls(unpacked), [5])

    def test_follows_import_aliases_and_direct_imports(self):
        aliased = "import subprocess as sp\nsp.run(['node', '-e', 's'])\n"
        self.assertEqual(bare_child_calls(aliased), [2])
        direct = "from subprocess import run\nrun(['ffmpeg', 'x'])\n"
        self.assertEqual(bare_child_calls(direct), [2])
        renamed = "from subprocess import check_output as out\nout(['ffprobe', 'x'])\n"
        self.assertEqual(bare_child_calls(renamed), [2])
        self.assertEqual(bare_child_calls("from subprocess import run\nrun(['git', 'init'])\n"), [])
        self.assertEqual(bare_child_calls("def run(x):\n    pass\nrun(['node'])\n"), [])

    def test_leaves_the_helper_and_other_children_alone(self):
        self.assertEqual(bare_child_calls("retry.run(['ffmpeg', 'x'])\n"), [])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['git', 'init'])\n"), [])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['git', 'commit', '-m', 'render'])\n"), [])
        unpacked = "import subprocess\ndef go():\n    git = ['git', '-C', 'x']\n    subprocess.run([*git, 'commit', '-m', 'render'])\n"
        self.assertEqual(bare_child_calls(unpacked), [])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['git', 'commit', '-m', 'note'])\n"), [])
        self.assertEqual(bare_child_calls("import subprocess\nsubprocess.run(['swift', 'build'])\n"), [])


class SweepTests(unittest.TestCase):
    def test_no_new_bare_child_in_tests(self):
        found = scan()
        fresh = {path: lines for path, lines in found.items() if path not in PENDING}
        self.assertEqual(fresh, {}, 'spawn render, ffmpeg and node children through simvltanea.subprocess_retry.run '
                                    '(from simvltanea import subprocess_retry as retry; retry.run(...))')

    def test_pending_lists_only_files_still_holding_bare_children(self):
        found = scan()
        stale = sorted(path for path in PENDING if path not in found)
        self.assertEqual(stale, [], 'converted already: remove these files from PENDING')


if __name__ == '__main__':
    unittest.main()
