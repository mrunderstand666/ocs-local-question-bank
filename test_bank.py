"""HTTP integration tests using a random loopback port and no browser state."""
import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener

from bank_server import Bank, make_server, ocs_config


class BankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = Bank(Path(__file__).with_name('seed.json'))
        cls.server = make_server(cls.bank, 0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.opener = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def get(self, path):
        with self.opener.open(f'http://127.0.0.1:{self.port}{path}', timeout=4) as response:
            return json.load(response)

    def test_all_answers_over_http(self):
        self.assertEqual(len(self.bank.questions), 150)
        for q in self.bank.questions:
            with self.subTest(id=q['id']):
                options = '\n'.join(o['label'] + '. ' + o['text'] for o in q['options'])
                result = self.get('/search?' + urlencode({'title': q['question'], 'type': q['type'], 'options': options}))
                self.assertTrue(any(r['id'] == q['id'] and r['answer'] == q['answer'] for r in result['results']))

    def test_empty_unknown_and_mismatched_options(self):
        for title in ('', '不存在的测试题目-xyz'):
            self.assertEqual(self.get('/search?' + urlencode({'title': title}))['results'], [])
        q = next(q for q in self.bank.questions if q['type'] == 'single')
        self.assertEqual(self.bank.search(q['question'], options='不匹配的选项')['results'], [])

    def test_normalization_and_reordered_options(self):
        q = self.bank.questions[0]
        title = '【单选题】 1. ' + q['question'] + '（1.0分）'
        options = '\n'.join(o['text'] for o in reversed(q['options']))
        self.assertEqual(self.bank.search(title, q['type'], options)['results'][0]['answer'], q['answer'])

    def test_completion_and_absent_options(self):
        q = next(q for q in self.bank.questions if q['id'] == '53546')
        for options in ('', 'undefined', 'null', '${options}'):
            self.assertEqual(self.bank.search(q['question'], options=options)['results'][0]['answer'], '义务')

    def test_ambiguous_stem(self):
        first = copy.deepcopy(self.bank.questions[0])
        second = copy.deepcopy(first)
        second['id'] = 'conflict'
        second['answer'] = '不同的答案'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.json'
            path.write_text(json.dumps({'questions': [first, second]}), encoding='utf-8')
            self.assertEqual(Bank(path).search(first['question'])['results'], [])

    def test_health_config_and_head(self):
        self.assertEqual(self.get('/health')['questions'], 150)
        self.assertEqual(self.get('/ocs-config'), ocs_config(self.port))
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        try:
            conn.request('HEAD', '/search')
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'')
        finally:
            conn.close()

    def test_host_and_missing_route(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        try:
            conn.request('GET', '/health', headers={'Host': 'outside.invalid'})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            conn.request('GET', '/not-an-endpoint')
            response = conn.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
