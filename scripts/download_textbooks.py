"""Archive public primary-math PDFs and the openly accessible PEP 2022 topic.

Run with Python + Pillow/reportlab/pypdf (Codex bundled document runtime works).
No login, challenge solving or decryption. Stops on 401/403; complete books only
are published to index.json. Re-running resumes verified JPEG page downloads.
--mirror-lower imports six identified lower-volume archive PDFs separately.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE='https://bp.pep.com.cn/xsjc2022/index.html'
EDITION='pep-2022-topic'


def fetch(url, limit=16_000_000, host='download.pep.com.cn'):
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'AI-Teacher-Textbook-Archive/1.0'}),timeout=30) as response:
                if response.url.split('/')[2]!=host:
                    raise ValueError('Unexpected resource redirect')
                data=response.read(limit+1)
                if len(data)>limit:raise ValueError('Unexpected resource size')
                return data
        except HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt==2:raise
        except (TimeoutError,ConnectionError):
            if attempt==2:raise
        time.sleep(1+attempt)


def valid_image(data):
    if not data.startswith(b'\xff\xd8\xff'):raise ValueError('Expected a public JPEG page')
    with Image.open(io.BytesIO(data)) as image:
        image.verify()


def atomic_json(path,value):
    temporary=path.with_suffix('.json.next')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(path)


def download_book(grade,output):
    material=f'pep-primary-math-g{grade}-t1'
    reader=f'https://download.pep.com.cn/xsxjc/22xjcsx{grade}1x/'
    folder=output/material/EDITION
    pages=folder/'pages';pages.mkdir(parents=True,exist_ok=True)
    config=fetch(reader+'mobile/javascript/config.js').decode('utf-8-sig')
    match=re.search(r'bookConfig.totalPageCount\s*=\s*(\d+)',config)
    if not match or not 30<=int(match[1])<=300:raise ValueError('Invalid published page count')
    count=int(match[1])
    # Accept only the documented public-image path; never decrypt protected pages.
    if 'bookConfig.normalPath="../files/mobile/"' not in config:
        raise ValueError('Unsupported public reader image format')
    (folder/'source-config.js').write_text(config,encoding='utf-8')
    print(f'{material}: {count} pages, downloading public images',flush=True)
    def page(number):
        destination=pages/f'{number:04}.jpg'
        if destination.exists():
            try:valid_image(destination.read_bytes());return
            except ValueError:pass
        data=fetch(reader+f'files/mobile/{number}.jpg');valid_image(data)
        temporary=destination.with_suffix('.jpg.part');temporary.write_bytes(data);temporary.replace(destination)
        time.sleep(.15)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(page,n):n for n in range(1,count+1)}
        done=0
        try:
            for job in as_completed(jobs):
                job.result();done+=1
                if done%25==0 or done==count:print(f'{material}: {done}/{count}',flush=True)
        except Exception:
            for job in jobs:job.cancel()
            raise
    temporary=folder/'document.pdf.part'
    pdf=canvas.Canvas(str(temporary),pageCompression=1)
    pdf.setTitle(f'PEP primary math grade {grade} upper - 2022 topic archive')
    pdf.setAuthor('People\'s Education Press (source pages)')
    pdf.setSubject('Local image compilation of the official 2022-topic reader; not a current-edition claim')
    checks=[]
    for n in range(1,count+1):
        file=pages/f'{n:04}.jpg'
        data=file.read_bytes();valid_image(data)
        with Image.open(io.BytesIO(data)) as image:width,height=image.size
        w,h=width*.5,height*.5
        pdf.setPageSize((w,h));pdf.drawImage(ImageReader(io.BytesIO(data)),0,0,width=w,height=h);pdf.showPage()
        checks.append({'page':n,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
    pdf.save()
    with temporary.open('rb') as stream:
        if len(PdfReader(stream).pages)!=count:raise ValueError('PDF page count mismatch')
    file=folder/'document.pdf';temporary.replace(file)
    record={'material_id':material,'edition_id':EDITION,'label':'2022 年专题存档（历史参考）',
        'source_url':ARCHIVE,'reader_url':reader,'format':'image_pdf','page_count':count,
        'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
        'imported_at':datetime.now(timezone.utc).isoformat(),'text_extracted':False,
        'edition_note':'与官方当前目录独立保存；具体版次请核对版权页。'}
    atomic_json(folder/'manifest.json',{**record,'pages':checks})
    return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'data'/'materials')
    parser.add_argument('--grades',nargs='+',type=int,choices=range(1,7),default=list(range(1,7)))
    parser.add_argument('--mirror-lower',action='store_true',help='Import identified public lower-volume archive PDFs instead of upper volumes')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    index_path=output/'index.json'
    index=json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {'schema_version':1,'resources':[]}
    failures=[]
    for grade in args.grades:
        try:
            record=download_mirror_lower(grade,output) if args.mirror_lower else download_book(grade,output)
            index['resources']=[r for r in index['resources'] if (r['material_id'],r['edition_id'])!=(record['material_id'],record['edition_id'])]+[record]
            atomic_json(index_path,index)
            print(f"SAVED {record['material_id']}: {record['page_count']} pages, {record['bytes']} bytes",flush=True)
        except Exception as error:
            failures.append(grade);print(f'FAILED grade {grade}: {type(error).__name__}: {error}',flush=True)
    print('Completed editions:',len(index['resources']),'failed grades:',failures,flush=True)
    if failures:raise SystemExit(1)


def download_mirror_lower(grade,output):
    sources=json.loads((ROOT/'backend/resources/textbooks/mirror_sources.json').read_text(encoding='utf-8'))
    material=f'pep-primary-math-g{grade}-t2'
    source=next(b for b in sources['books'] if b['material_id']==material)
    eid=source['edition_id'];folder=output/material/eid;folder.mkdir(parents=True,exist_ok=True)
    file=folder/'document.pdf'
    data=file.read_bytes() if file.exists() else fetch(source['reader_url'],limit=100_000_000,host='raw.githubusercontent.com')
    if len(data)!=source['bytes'] or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=source['git_blob_sha']:
        raise ValueError('Mirror file identity changed; review before importing')
    if not data.startswith(b'%PDF-'):raise ValueError('Not a PDF')
    pdf=PdfReader(io.BytesIO(data))
    if pdf.is_encrypted:raise ValueError('Encrypted PDF not supported')
    if not 30<=len(pdf.pages)<=300:raise ValueError('Unexpected page count')
    title=['一年级','二年级','三年级','四年级','五年级','六年级'][grade-1]
    text=''.join(page.extract_text() or '' for page in list(pdf.pages[:6])+list(pdf.pages[-2:]))
    compact=re.sub(r'\s+','',text)
    if not all(s in compact for s in (title,'下册','数学','人民教育出版社')):
        raise ValueError('PDF title/publisher needs manual verification')
    root=pdf.trailer['/Root']
    if '/OpenAction' in root or '/AA' in root or '/JavaScript' in (root.get('/Names') or {}):
        raise ValueError('Active PDF features require review')
    temporary=file.with_suffix('.pdf.part');temporary.write_bytes(data);temporary.replace(file)
    record=dict(material_id=material,edition_id=eid,label=sources['label'],source_url=sources['source_url'],
        reader_url=source['reader_url'],format='source_pdf',page_count=len(pdf.pages),bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),git_blob_sha=source['git_blob_sha'],
        imported_at=datetime.now(timezone.utc).isoformat(),text_extracted=False,
        edition_note=sources['note'])
    atomic_json(folder/'manifest.json',record)
    (folder/'title-verification.txt').write_text(text,encoding='utf-8')
    return record


if __name__=='__main__':main()
