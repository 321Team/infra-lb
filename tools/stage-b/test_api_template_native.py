"""Offline native-kubectl regression. Set KUBECTL_TEST_BIN; never contacts an API."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import collect_api_precheck as api

KUBECTL = os.environ.get('KUBECTL_TEST_BIN') or shutil.which('kubectl')


@unittest.skipUnless(KUBECTL, 'native kubectl unavailable; not a native-template PASS')
class NativeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / 'synthetic-config.json'
        self.base = {
            'apiVersion': 'v1', 'kind': 'Config',
            'clusters': [{'name': 'kubernetes', 'cluster': {
                'server': 'https://192.0.2.1:6443', 'certificate-authority-data': 'RkFLRV9DQQ=='}}],
            'users': [{'name': 'kubernetes-admin', 'user': {'token': 'FAKE_SECRET_SENTINEL'}}],
            'contexts': [{'name': api.CONTEXT, 'context': {'cluster': 'kubernetes', 'user': 'kubernetes-admin'}}],
            'current-context': api.CONTEXT}

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, data, template=api.CONFIG_TEMPLATE):
        self.config.write_text(json.dumps(data))
        return subprocess.run([KUBECTL, '--kubeconfig=' + str(self.config), '--context=' + api.CONTEXT,
                               'config', 'view', '--minify', '-o', 'go-template=' + template],
                              capture_output=True, text=True, timeout=10,
                              env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': self.tmp.name})

    def test_reported_old_template_error_is_reproduced(self):
        broken = api.CONFIG_TEMPLATE.replace(r'{{"\n"}}', '{{"\n"}}')
        self.assertNotEqual(broken, api.CONFIG_TEMPLATE)
        result = self.render(self.base, broken)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unterminated quoted string', result.stderr)

    def test_corrected_template_returns_six_flags_without_credentials(self):
        result = self.render(self.base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout.splitlines(), api.EXPECTED_FLAGS)
        self.assertNotIn('FAKE_SECRET_SENTINEL', result.stdout + result.stderr)

    def test_security_flags_remain_detectable(self):
        cases = [
            ('cluster', 'proxy-url', 'http://FAKE_PROXY_SENTINEL.invalid', 'proxy=yes'),
            ('cluster', 'insecure-skip-tls-verify', True, 'insecure=yes'),
            ('cluster', 'certificate-authority-data', None, 'ca=no'),
            ('user', 'exec', {'apiVersion': 'client.authentication.k8s.io/v1',
                             'command': '/nonexistent/never-execute', 'interactiveMode': 'Never'}, 'exec=yes'),
            ('user', 'auth-provider', {'name': 'synthetic', 'config': {'x': 'FAKE_PROVIDER_SENTINEL'}}, 'provider=yes'),
            ('user', 'as', 'FAKE_IMPERSONATION_SENTINEL', 'impersonation=yes'),
            ('user', 'as-uid', '12345', 'impersonation=yes'),
            ('user', 'as-groups', ['FAKE_GROUP_SENTINEL'], 'impersonation=yes'),
            ('user', 'as-user-extra', {'x': ['FAKE_EXTRA_SENTINEL']}, 'impersonation=yes'),
        ]
        for kind, key, value, expected in cases:
            with self.subTest(key=key):
                data = copy.deepcopy(self.base)
                target = data['clusters'][0]['cluster'] if kind == 'cluster' else data['users'][0]['user']
                if value is None:
                    del target[key]
                else:
                    target[key] = value
                result = self.render(data)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual(len(result.stdout.splitlines()), 6)
                self.assertIn(expected, result.stdout.splitlines())
                self.assertNotEqual(result.stdout.splitlines(), api.EXPECTED_FLAGS)
                self.assertNotIn('SENTINEL', result.stdout + result.stderr)
