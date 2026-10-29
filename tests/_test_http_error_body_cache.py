import io
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wb_proxy as proxy


class HttpErrorBodyTest(unittest.TestCase):
    def error(self):
        return urllib.error.HTTPError('http://example.invalid', 400, 'bad', {},
                                      io.BytesIO(b'{"code":123,"message":"bad request"}'))

    @mock.patch.dict(os.environ, {'WB_CACHE_HTTP_ERROR_BODY': '1'})
    def test_opt_in_preserves_first_read_for_later_reader(self):
        error = self.error()
        body = b'{"code":123,"message":"bad request"}'
        self.assertEqual(proxy.read_http_error(error, 800), body)
        self.assertEqual(proxy.read_http_error(error, 600), body)

    def test_existing_body_and_limit_are_preserved(self):
        error = self.error()
        error.wb_body = b"cached upstream detail"
        self.assertEqual(proxy.read_http_error(error, 6), b"cached")
        self.assertEqual(proxy.read_http_error(error, 30), b"cached upstream detail")

    @mock.patch.dict(os.environ, {'WB_CACHE_HTTP_ERROR_BODY': '0'})
    def test_default_preserves_existing_consumption(self):
        error = self.error()
        self.assertTrue(proxy.read_http_error(error, 800))
        self.assertEqual(proxy.read_http_error(error, 600), b'')


if __name__ == '__main__':
    unittest.main()
