import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'))
import server

class FakeDetector:
    def health(self):return {'ready':True,'name':'test'}

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.DETECTOR=FakeDetector()
        cls.httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join()
    def request(self, method, route, body=None, headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=5)
        conn.request(method,route,body,headers or {})
        response=conn.getresponse();data=response.read();status=response.status;conn.close();return status,data
    def test_health(self):
        code,body=self.request('GET','/api/health');self.assertEqual(code,200);self.assertTrue(json.loads(body)['model']['ready'])
    def test_static_page(self):
        code,body=self.request('GET','/');self.assertEqual(code,200);self.assertIn('PCB Inspector'.encode(),body)
    def test_paths_cannot_read_model_or_backend(self):
        for path in ['/../models/config.json','/..%2fbackend/server.py','/samples/..%2fmodels/config.json']:
            self.assertEqual(self.request('GET',path)[0],404)
    def test_invalid_json_is_400(self):self.assertEqual(self.request('POST','/api/analyze','{')[0],400)
    def test_nonfinite_threshold_is_400(self):
        for value in ['NaN','Infinity','-Infinity']:
            self.assertEqual(self.request('POST','/api/analyze','{"threshold":'+value+'}')[0],400)
    def test_non_object_json_is_400(self):self.assertEqual(self.request('POST','/api/analyze','[]')[0],400)
    def test_bad_image_is_400(self):
        self.assertEqual(self.request('POST','/api/analyze',json.dumps({'image':'data:image/jpeg;base64,not-an-image'}))[0],400)
    def test_requires_confirmed_reference_variant(self):
        self.assertEqual(self.request('POST','/api/analyze',json.dumps({'same_board_confirmed':False,'variant':'A rev.2'}))[0],400)
        self.assertEqual(self.request('POST','/api/analyze',json.dumps({'same_board_confirmed':True,'variant':''}))[0],400)
    def test_invalid_roi_is_400(self):
        self.assertEqual(self.request('POST','/api/analyze',json.dumps({'same_board_confirmed':True,'variant':'A rev.2','roi':[.5,.5,.1,.9]}))[0],400)
    def test_invalid_area_is_400(self):
        self.assertEqual(self.request('POST','/api/analyze',json.dumps({'same_board_confirmed':True,'variant':'A rev.2','min_area':-1}))[0],400)
    def test_cross_origin_is_403(self):self.assertEqual(self.request('POST','/api/analyze','{}',{'Origin':'https://example.com'})[0],403)
    def test_oversize_is_413(self):self.assertEqual(self.request('POST','/api/analyze',None,{'Content-Length':str(server.MAX_BODY+1)})[0],413)
