"""Exercise the real sync script against isolated local Git histories."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('sync-upstream.sh').resolve()


def git(repo, *args):
    return subprocess.check_output(
        ['git', '-C', str(repo), *args], stderr=subprocess.STDOUT, text=True
    ).strip()


def put(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(repo, message):
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)


class SyncTests(unittest.TestCase):
    def exercise(self, case):
        with tempfile.TemporaryDirectory(prefix='glance-sync-test-') as directory:
            root = Path(directory)
            upstream, fork = root / 'upstream', root / 'fork'
            upstream.mkdir()
            git(upstream, 'init', '-qb', 'main')
            git(upstream, 'config', 'user.email', 'test@example.invalid')
            git(upstream, 'config', 'user.name', 'Test')
            put(upstream, 'Dockerfile', 'FROM golang:1.27.1-alpine3.24\n')
            put(upstream, 'app', 'base\n')
            put(upstream, '.github/workflows/shared.yml', 'original\n')
            put(upstream, '.github/workflows/deleted.yml', 'original\n')
            commit(upstream, 'base')
            git(root, 'clone', '-q', str(upstream), str(fork))
            git(fork, 'config', 'user.email', 'test@example.invalid')
            git(fork, 'config', 'user.name', 'Test')
            put(fork, '.github/workflows/shared.yml', 'fork\n')
            put(fork, '.github/workflows/deploy.yml', 'fork deploy\n')
            if case == 'code-conflict':
                put(fork, 'app', 'fork change\n')
            commit(fork, 'fork changes')
            base = git(fork, 'rev-parse', 'HEAD')
            git(fork, 'update-ref', 'refs/remotes/origin/main', base)
            if case == 'workflow-changes':
                put(upstream, '.github/workflows/shared.yml', 'upstream\n')
                put(upstream, '.github/workflows/new.yml', 'new\n')
                (upstream / '.github/workflows/deleted.yml').unlink()
            if case == 'code-conflict':
                put(upstream, 'app', 'upstream change\n')
            if case not in ('already-current', 'fetch-failure'):
                put(upstream, 'Dockerfile', 'FROM golang:1.27.3-alpine3.24\n')
                commit(upstream, 'upstream update')
            target = upstream / 'missing' if case == 'fetch-failure' else upstream
            git(fork, 'config', f'url.{target}.insteadOf',
                'https://github.com/glanceapp/glance.git')
            output, summary = root / 'output', root / 'summary'
            output.touch()
            summary.touch()
            result = subprocess.run(
                ['bash', str(SCRIPT)], cwd=fork, capture_output=True, text=True,
                env={**os.environ, 'GITHUB_OUTPUT': str(output),
                     'GITHUB_STEP_SUMMARY': str(summary)},
            )
            if case == 'fetch-failure':
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(git(fork, 'rev-parse', 'HEAD'), base)
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git(fork, 'status', '--porcelain'), '')
            self.assertEqual(git(fork, 'diff', base, 'HEAD', '--', '.github/workflows'), '')
            if case == 'code-conflict':
                self.assertIn('conflict=true', output.read_text())
                self.assertIn('app', summary.read_text())
                self.assertEqual(git(fork, 'rev-parse', 'HEAD'), base)
            elif case == 'already-current':
                self.assertEqual(git(fork, 'rev-parse', 'HEAD'), base)
            else:
                git(fork, 'merge-base', '--is-ancestor',
                    git(upstream, 'rev-parse', 'HEAD'), 'HEAD')
                self.assertIn('1.27.3', (fork / 'Dockerfile').read_text())

    def test_upstream_version_bump_merges(self):
        self.exercise('version-bump')

    def test_fork_workflows_survive_conflicts_additions_and_deletions(self):
        self.exercise('workflow-changes')

    def test_code_conflicts_abort_without_discarding_customizations(self):
        self.exercise('code-conflict')

    def test_current_fork_is_unchanged(self):
        self.exercise('already-current')

    def test_fetch_failure_does_not_report_success(self):
        self.exercise('fetch-failure')


class PublishTests(unittest.TestCase):
    def exercise(self, current):
        with tempfile.TemporaryDirectory(prefix='glance-publish-test-') as directory:
            root = Path(directory)
            # Test the promotion script without touching GitHub or a registry.
            git_stub = root / 'git'
            git_stub.write_text('#!/bin/sh\nprintf "'+current+'\trefs/heads/main\\n"\n')
            docker_stub = root / 'docker'
            docker_stub.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
            git_stub.chmod(0o755)
            docker_stub.chmod(0o755)
            calls, output = root / 'calls', root / 'output'
            output.touch()
            result = subprocess.run(
                ['bash', str(SCRIPT.with_name('publish-current-image.sh'))],
                capture_output=True, text=True,
                env={**os.environ, 'PATH': str(root)+os.pathsep+os.environ['PATH'],
                     'CALLS': str(calls), 'GITHUB_OUTPUT': str(output),
                     'IMAGE': 'example.invalid/glance', 'REVISION': 'built-commit'},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            if current == 'built-commit':
                self.assertEqual(calls.read_text().strip(),
                    'buildx imagetools create --tag example.invalid/glance:latest example.invalid/glance:built-commit')
                self.assertIn('current=true', output.read_text())
            else:
                self.assertFalse(calls.exists())
                self.assertEqual(output.read_text(), '')

    def test_current_build_can_publish_latest(self):
        self.exercise('built-commit')

    def test_stale_build_cannot_publish_latest_or_request_deployment(self):
        self.exercise('newer-commit')


if __name__ == '__main__':
    unittest.main()
