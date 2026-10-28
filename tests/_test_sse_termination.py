import io
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wb_proxy as proxy


class DoneOnly:
    def __iter__(self):
        yield b'data: [DONE]\n\n'
        raise AssertionError('read after terminal event')


class Read1Stream:
    def __init__(self):
        self.reads = 0

    def read1(self, size):
        self.reads += 1
        if self.reads > 1:
            raise AssertionError('read after terminal event')
        return (b'data: {"id":"x","choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
                b'data: {"id":"x","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                b'data: {"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
                b'data: [DONE]\n\n')


@mock.patch.dict(os.environ, {"WB_STOP_AT_SSE_DONE": "1"})
class ProtocolRegression(unittest.TestCase):
    def test_default_keeps_reading_after_done(self):
        class Continued:
            reached_end = False
            def __iter__(self):
                yield b"data: [DONE]\n\n"
                self.reached_end = True
        with mock.patch.dict(os.environ, {"WB_STOP_AT_SSE_DONE": "0"}):
            for consume in (lambda stream: proxy.aggregate_stream(stream, 'model', 'id'),
                            lambda stream: list(proxy.stream_responses_events(stream, 'model', {})),
                            self.run_chat):
                stream = Continued()
                consume(stream)
                self.assertTrue(stream.reached_end)

    def test_aggregate_stops_at_done(self):
        proxy.aggregate_stream(DoneOnly(), 'model', 'id')

    def test_responses_stops_at_done(self):
        list(proxy.stream_responses_events(DoneOnly(), 'model', {}))

    def run_chat(self, stream):
        output = io.BytesIO()
        handler = types.SimpleNamespace(wfile=output, _key_id=lambda: None)
        account = types.SimpleNamespace(uid='test')
        with mock.patch.object(proxy.wb_settings, 'egress_backoff_enabled', return_value=False), \
             mock.patch.object(proxy, 'record_upstream_usage'), \
             mock.patch.object(proxy, 'record_error') as error:
            proxy.Handler._chat_stream_response(handler, stream, 'model', None, account,
                                                time.time(), headers_sent=True)
        error.assert_not_called()
        return output.getvalue()

    def test_chat_stops_at_done(self):
        self.assertIn(b'data: [DONE]\n\n', self.run_chat(DoneOnly()))

    def test_chat_read1_delivers_finish_usage_and_done_without_another_read(self):
        stream = Read1Stream()
        output = self.run_chat(stream)
        self.assertEqual(stream.reads, 1)
        self.assertIn(b'"finish_reason": "stop"', output)
        self.assertIn(b'"total_tokens": 2', output)
        self.assertIn(b'data: [DONE]\n\n', output)


if __name__ == '__main__':
    unittest.main()
