"""Curated references and complete local textbook editions. No remote fetches."""
from copy import deepcopy
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

CATALOG_PATH = Path(__file__).parent / 'resources' / 'textbooks' / 'catalog.json'
OFFICIAL_HOSTS = {'jc.pep.com.cn', 'book.pep.com.cn', 'bp.pep.com.cn', 'download.pep.com.cn'}
router = APIRouter(prefix='/api/materials', tags=['materials'])
MATERIALS_DIR = Path(os.getenv('AITEACHER_MATERIALS_DIR', str(Path(__file__).resolve().parents[1] / 'data' / 'materials')))
logger = logging.getLogger(__name__)


def validate_catalog(value):
    """Fail closed on malformed provenance, duplicate IDs or unsafe outbound links."""
    seen, semesters = set(), set()
    def check_url(url):
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname not in OFFICIAL_HOSTS or parts.username or parts.password or parts.port:
            raise ValueError('Textbook links must use an official HTTPS source')
    check_url(value['source']['url'])
    check_url(value['source']['catalog_asset_url'])
    for book in value['books']:
        grade, term = book['grade'], book['term']
        if type(grade) is not int or grade not in range(1, 7) or type(term) is not int or term not in (1, 2):
            raise ValueError('Invalid textbook grade/term')
        if book['id'] in seen or book['semester_id'] in semesters:
            raise ValueError('Duplicate textbook or semester')
        if book['id'] != f'pep-primary-math-g{grade}-t{term}' or book['semester_id'] != f'primary-math-g{grade}-t{term}':
            raise ValueError('Textbook semester mismatch')
        if book['subject'] != '数学' or book['school_system'] != '义务教育（六三学制）':
            raise ValueError('Unexpected textbook series')
        if book['content_status'] != 'reference_only' or book['full_text_available'] is not False or book['toc_available'] is not False:
            raise ValueError('This catalog contains references only')
        seen.add(book['id'])
        semesters.add(book['semester_id'])
        check_url(book['reader_url'])
        check_url(book['source_url'])
        for reference in book['historical_references']:
            check_url(reference['reader_url'])
            check_url(reference['source_url'])
    if len(seen) != 12:
        raise ValueError('Expected twelve primary math textbooks')
    return value


@lru_cache(maxsize=1)
def catalog():
    return validate_catalog(json.loads(CATALOG_PATH.read_text(encoding='utf-8')))


def edition_file(material_id, edition_id):
    # Fixed storage layout; neither request nor manifest supplies a filesystem path.
    if material_id not in {b['id'] for b in catalog()['books']} or edition_id not in ('pep-2022-topic','public-mirror-archive'):
        return None
    root = MATERIALS_DIR.resolve()
    file = (root / material_id / edition_id / 'document.pdf').resolve()
    return file if file.is_relative_to(root) else None


@lru_cache(maxsize=1)
def mirror_sources():
    return json.loads((CATALOG_PATH.parent / 'mirror_sources.json').read_text(encoding='utf-8'))


def expected_source(book, eid):
    if eid == 'pep-2022-topic' and book['term'] == 1:
        return dict(source_url='https://bp.pep.com.cn/xsjc2022/index.html',
                    reader_url=f"https://download.pep.com.cn/xsxjc/22xjcsx{book['grade']}1x/",
                    label='2022 年专题存档（历史参考）',format='image_pdf',origin='official_archive')
    if eid == 'public-mirror-archive' and book['term'] == 2:
        source = mirror_sources()
        row = next((r for r in source['books'] if r['material_id'] == book['id']), None)
        if row:
            return dict(source_url=source['source_url'],reader_url=row['reader_url'],
                        label=source['label'],format='source_pdf',origin='public_mirror',git_blob_sha=row['git_blob_sha'])
    return None


def local_editions():
    try:
        value = json.loads((MATERIALS_DIR / 'index.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.warning('Local textbook index unavailable or invalid')
        return []
    records = []
    seen = set()
    if not isinstance(value, dict) or value.get('schema_version') != 1 or not isinstance(value.get('resources'), list):
        return []
    for row in value['resources']:
        try:
            if not isinstance(row, dict):
                continue
            mid, eid = row['material_id'], row['edition_id']
            book = next((b for b in catalog()['books'] if b['id'] == mid), None)
            if not book or (mid, eid) in seen:
                continue
            source = expected_source(book, eid)
            if not source:
                continue
            file = edition_file(mid, eid)
            if not file or not file.is_file() or type(row['bytes']) is not int or file.stat().st_size != row['bytes']:
                continue
            if type(row['page_count']) is not int or not 30 <= row['page_count'] <= 300 or row.get('format') != source['format']:
                continue
            if any(row.get(key) != source[key] for key in ('source_url','reader_url')):
                continue
            if 'git_blob_sha' in source and row.get('git_blob_sha') != source['git_blob_sha']:
                continue
            if not isinstance(row.get('sha256'), str) or len(row['sha256']) != 64 or any(c not in '0123456789abcdef' for c in row['sha256']):
                continue
            # Explicit public fields: never expose local filenames or unexpected metadata.
            record = {key: row[key] for key in ('material_id','edition_id','page_count','bytes','sha256','imported_at','source_url','reader_url')}
            record.update(label=source['label'],format=source['format'],origin=source['origin'],text_extracted=False,
                          edition_note='历史存档，与官方当前目录独立保存；版次以版权页为准。',
                          read_url=f'/api/materials/{mid}/editions/{eid}/pdf',
                          download_url=f'/api/materials/{mid}/editions/{eid}/pdf?download=true')
            records.append(record)
            seen.add((mid, eid))
        except (KeyError, TypeError, ValueError, OSError):
            logger.warning('Ignoring invalid or incomplete local textbook edition')
    return records


def with_editions(book, editions):
    result = deepcopy(book)
    result['local_editions'] = [e for e in editions if e['material_id'] == book['id']]
    return result


@router.get('')
def list_materials(grade: int | None = Query(default=None, ge=1, le=6),
                   term: int | None = Query(default=None, ge=1, le=2),
                   semester_id: str | None = Query(default=None, max_length=80),
                   q: str = Query(default='', max_length=100)):
    result = deepcopy(catalog())
    editions = local_editions()
    query = q.strip().casefold()
    result['books'] = [book for book in result['books']
        if (grade is None or book['grade'] == grade)
        and (term is None or book['term'] == term)
        and (semester_id is None or book['semester_id'] == semester_id)
        and (not query or query in ' '.join(str(book[key]) for key in
             ('title', 'grade_label', 'volume', 'subject', 'publisher', 'series')).casefold())]
    result['total'] = len(result['books'])
    result['books'] = [with_editions(book, editions) for book in result['books']]
    result['local_book_count'] = sum(bool(book['local_editions']) for book in result['books'])
    return result


@router.get('/{material_id}')
def get_material(material_id: str):
    for book in catalog()['books']:
        if book['id'] == material_id:
            return {'book': with_editions(book, local_editions()), 'verified_at': catalog()['verified_at'],
                    'source': deepcopy(catalog()['source'])}
    raise HTTPException(404, '教材资料不存在。')


@router.get('/{material_id}/editions/{edition_id}/pdf')
def read_local_pdf(material_id: str, edition_id: str, request: Request, download: bool = False):
    edition = next((e for e in local_editions() if e['material_id'] == material_id and e['edition_id'] == edition_id), None)
    if not edition:
        raise HTTPException(404, '这份本地教材尚未完整入库或文件不可用。')
    file = edition_file(material_id, edition_id)
    stat = file.stat()
    response = FileResponse(file, stat_result=stat, media_type='application/pdf',filename=f'{material_id}-{edition_id}.pdf',
                        content_disposition_type='attachment' if download else 'inline',
                        headers={'X-Content-Type-Options':'nosniff','Accept-Ranges':'bytes'})
    # The deployed Starlette predates FileResponse range support. PDFs need it
    # to jump to later pages without re-downloading the entire book.
    value = request.headers.get('range')
    if not value or not value.startswith('bytes='):
        return response
    if_range = request.headers.get('if-range')
    if if_range and if_range not in (response.headers.get('etag'),response.headers.get('last-modified')):
        return response
    match = re.fullmatch(r'bytes=([0-9]{0,20})-([0-9]{0,20})',value)
    size = stat.st_size
    start,end = 0,size-1
    valid = match and any(match.groups())
    if valid:
        left,right = match.groups()
        if left:
            start = int(left)
            end = min(int(right),size-1) if right else size-1
        else:
            start = max(0,size-int(right))
            valid = int(right)>0
        valid = valid and start<=end and start<size
    if not valid:
        return Response(status_code=416,headers={'Content-Range':f'bytes */{size}','Accept-Ranges':'bytes'})
    def chunks():
        with file.open('rb') as stream:
            stream.seek(start)
            remaining = end-start+1
            while remaining:
                chunk = stream.read(min(65536,remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    headers = dict(response.headers)
    headers.update({'content-range':f'bytes {start}-{end}/{size}','content-length':str(end-start+1)})
    return StreamingResponse(chunks(),status_code=206,media_type='application/pdf',headers=headers)
