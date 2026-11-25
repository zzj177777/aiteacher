"""The library is an offline reference index, not invented textbook content."""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend import materials


class HttpClient:
    def __init__(self, url):
        self.url = url

    def get(self, path, params=None):
        return self.call(path+('?' + urlencode(params) if params else ''), 'GET')

    def post(self, path, json=None):
        return self.call(path, 'POST', json)

    def call(self, path, method, body=None):
        request = Request(self.url+path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json'})
        try:
            response=urlopen(request, timeout=5)
        except HTTPError as error:
            response=error
        with response:
            data=json.load(response)
            return type('Response', (), {'status_code':response.code, 'json':lambda self:data})()


class MaterialsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        cls.client=HttpClient(f'http://127.0.0.1:{port}')
        cls.materials_dir=Path(cls.temp.name)/'materials'
        cls.materials_dir.mkdir()
        env=dict(os.environ, AI_API_URL='',AI_API_KEY='',AI_MODEL='')
        env['AITEACHER_MATERIALS_DIR']=str(cls.materials_dir)
        for key,name in [('AITEACHER_DB','classroom'),('AITEACHER_USAGE_DB','usage'),
                         ('AITEACHER_MODEL_DEBUG_DB','debug'),('AITEACHER_PLAIN_LANGUAGE_DB','plain')]:
            env[key]=str(Path(cls.temp.name)/(name+'.sqlite3'))
        cls.process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(port)],
            cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(80):
            try:
                if cls.client.get('/api/health').status_code==200:
                    return
            except OSError:
                time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()
        raise RuntimeError('Isolated materials test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.temp.cleanup()

    def test_twelve_official_books_with_explicit_content_status(self):
        response = self.client.get('/api/materials')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['total'], 12)
        self.assertEqual({(b['grade'], b['term']) for b in result['books']},
                         {(g, t) for g in range(1, 7) for t in (1, 2)})
        self.assertEqual(result['verified_at'], '2026-11-25')
        for book in result['books']:
            self.assertEqual(book['school_system'], '义务教育（六三学制）')
            self.assertEqual(book['content_status'], 'reference_only')
            self.assertFalse(book['full_text_available'])
            self.assertFalse(book['toc_available'])
            self.assertEqual(book['edition'], '具体版次待核验')
            self.assertEqual(book['reader_url'], 'https://book.pep.com.cn/'+book['catalog_record_id']+'/')
            self.assertEqual(len(book['historical_references']), 1 if book['term'] == 1 else 0)
            self.assertNotIn('chapters', book)
            self.assertNotIn('content', book)

    def test_filters_and_detail_are_stable(self):
        result = self.client.get('/api/materials', params={'semester_id':'primary-math-g3-t1'}).json()
        self.assertEqual([b['id'] for b in result['books']], ['pep-primary-math-g3-t1'])
        book = result['books'][0]
        self.assertEqual(book['catalog_record_id'], '1221001301251')
        self.assertEqual(self.client.get('/api/materials/'+book['id']).json()['book'], book)
        result = self.client.get('/api/materials', params={'grade':4,'term':2,'q':'数学'}).json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['books'][0]['catalog_record_id'], '1221001402131')
        self.assertEqual(self.client.get('/api/materials',params={'q':'英语'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/materials',params={'semester_id':'not-a-semester'}).json()['total'], 0)

    def test_invalid_inputs_and_read_only_contract(self):
        for params in ({'grade':0},{'grade':7},{'term':3},{'q':'x'*101}):
            self.assertEqual(self.client.get('/api/materials',params=params).status_code, 422)
        self.assertEqual(self.client.get('/api/materials/no-such-book').status_code, 404)
        self.assertEqual(self.client.post('/api/materials',json={'url':'http://localhost/'}).status_code, 405)

    def test_reads_do_not_fetch_readers_or_call_models(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected remote fetch')), \
             patch('backend.tutor.complete',side_effect=AssertionError('Unexpected model call')):
            self.assertEqual(materials.list_materials(None,None,None,'')['total'], 12)
            self.assertEqual(materials.get_material('pep-primary-math-g1-t1')['book']['grade'], 1)

    def test_reject_misleading_content_unsafe_links_and_duplicates(self):
        for mutate in (
            lambda b:b.update(reader_url='https://book.pep.com.cn.evil.test/book'),
            lambda b:b.update(reader_url='http://book.pep.com.cn/book'),
            lambda b:b.update(reader_url='https://user@book.pep.com.cn/book'),
            lambda b:b.update(reader_url='https://book.pep.com.cn:8443/book'),
            lambda b:b.update(full_text_available=True),
            lambda b:b.update(semester_id='primary-math-g6-t2'),
            lambda b:b.update(school_system='盲校义务教育'),
        ):
            value=deepcopy(materials.catalog())
            mutate(value['books'][0])
            with self.assertRaises(ValueError):
                materials.validate_catalog(value)
        value=deepcopy(materials.catalog())
        value['books'][1]=value['books'][0]
        with self.assertRaises(ValueError):
            materials.validate_catalog(value)

    def test_filter_does_not_mutate_shared_catalog(self):
        self.client.get('/api/materials',params={'grade':1})
        self.assertEqual(self.client.get('/api/materials').json()['total'], 12)

    def test_local_pdf_read_download_range_and_missing_file(self):
        import hashlib
        mid,eid='pep-primary-math-g3-t1','pep-2022-topic'
        folder=self.materials_dir/mid/eid
        folder.mkdir(parents=True,exist_ok=True)
        # Deterministic small byte fixture for HTTP streaming, not a real textbook.
        pdf=b'%PDF-1.4\n'+b'fixture '*100+b'\n%%EOF\n'
        file=folder/'document.pdf';file.write_bytes(pdf)
        record=dict(material_id=mid,edition_id=eid,format='image_pdf',page_count=124,
            bytes=len(pdf),sha256=hashlib.sha256(pdf).hexdigest(),imported_at='2026-11-25',
            source_url='https://bp.pep.com.cn/xsjc2022/index.html',reader_url='https://download.pep.com.cn/xsxjc/22xjcsx31x/',
            path='C:/private/secret.env')
        index=self.materials_dir/'index.json'
        index.write_text(json.dumps(dict(schema_version=1,resources=[record])),encoding='utf-8')
        path=f'/api/materials/{mid}/editions/{eid}/pdf'
        try:
            response=self.client.get('/api/materials')
            listing=response.json()
            self.assertEqual(listing['local_book_count'],1)
            book=next(b for b in listing['books'] if b['id']==mid)
            edition=book['local_editions'][0]
            self.assertEqual(edition['read_url'],path)
            self.assertFalse(edition['text_extracted'])
            self.assertNotIn('path',edition)
            self.assertEqual(book['edition'],'具体版次待核验')
            for suffix,disposition in [('', 'inline'),('?download=true','attachment')]:
                with urlopen(self.client.url+path+suffix,timeout=5) as r:
                    self.assertEqual(r.headers['Content-Type'],'application/pdf')
                    self.assertTrue(r.headers['Content-Disposition'].startswith(disposition))
                    self.assertEqual(r.read(),pdf)
            with urlopen(Request(self.client.url+path,headers={'Range':'bytes=0-7'}),timeout=5) as r:
                self.assertEqual(r.status,206)
                self.assertEqual(r.read(),b'%PDF-1.4')
            with urlopen(Request(self.client.url+path,headers={'Range':'bytes=-6'}),timeout=5) as r:
                self.assertEqual(r.status,206)
                self.assertEqual(r.read(),pdf[-6:])
            with urlopen(Request(self.client.url+path,headers={'Range':'bytes=0-7','If-Range':'stale'}),timeout=5) as r:
                self.assertEqual(r.status,200)
                self.assertEqual(r.read(),pdf)
            for invalid in ('bytes=99999-','bytes=8-4','bytes=0-1,4-5','bytes=-0','bytes='+'9'*100+'-'):
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(self.client.url+path,headers={'Range':invalid}),timeout=5)
                self.assertEqual(error.exception.code,416)
                error.exception.close()
            file.write_bytes(pdf[:40])
            self.assertEqual(self.client.get(path).status_code,404)
            self.assertEqual(self.client.get('/api/materials').json()['local_book_count'],0)
            file.unlink()
            self.assertEqual(self.client.get(path).status_code,404)
        finally:
            index.unlink(missing_ok=True)
            file.unlink(missing_ok=True)

    def test_reject_untrusted_local_manifest_and_path_parameters(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(materials,'MATERIALS_DIR',Path(directory)):
            index=Path(directory)/'index.json'
            for payload in ('bad json','[]','{"schema_version":1,"resources":[{"material_id":"../private"}]}'):
                index.write_text(payload,encoding='utf-8')
                self.assertEqual(materials.local_editions(),[])
            self.assertIsNone(materials.edition_file('../private','pep-2022-topic'))
            self.assertIsNone(materials.edition_file('pep-primary-math-g1-t1','../../secret'))
        for mid,eid in [('unknown','pep-2022-topic'),('pep-primary-math-g1-t2','pep-2022-topic'),('pep-primary-math-g1-t1','other')]:
            self.assertEqual(self.client.get(f'/api/materials/{mid}/editions/{eid}/pdf').status_code,404)

    def test_mirror_source_identity_stays_separate_from_current_catalog(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(materials,'MATERIALS_DIR',Path(directory)):
            source=materials.mirror_sources()['books'][0]
            file=Path(directory)/source['material_id']/source['edition_id']/'document.pdf'
            file.parent.mkdir(parents=True);file.write_bytes(b'%PDF-fixture')
            record={**source,'source_url':materials.mirror_sources()['source_url'],
                    'format':'source_pdf','page_count':110,'bytes':file.stat().st_size,
                    'sha256':'a'*64,'imported_at':'2026-11-25'}
            index=Path(directory)/'index.json'
            index.write_text(json.dumps(dict(schema_version=1,resources=[record])),encoding='utf-8')
            result=materials.local_editions()
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['origin'],'public_mirror')
            self.assertEqual(result[0]['label'],'公开镜像存档（旧版参考）')
            record['git_blob_sha']='wrong'
            index.write_text(json.dumps(dict(schema_version=1,resources=[record])),encoding='utf-8')
            self.assertEqual(materials.local_editions(),[])


if __name__ == '__main__':
    unittest.main()
