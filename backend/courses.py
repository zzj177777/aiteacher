"""Persistent course folders for anonymous, capability-authenticated learners."""
from datetime import datetime, timezone
import hashlib
import json
import secrets
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from . import course_scope, curriculum


def now():
    return datetime.now(timezone.utc).isoformat()


def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS learning_libraries(
      id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS courses(
      id TEXT PRIMARY KEY, library_id TEXT NOT NULL, title TEXT NOT NULL,
      description TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS courses_library ON courses(library_id);
    CREATE TABLE IF NOT EXISTS course_sessions(
      session_id TEXT PRIMARY KEY, library_id TEXT NOT NULL, course_id TEXT,
      title TEXT NOT NULL, added_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS course_sessions_library ON course_sessions(library_id,course_id);
    """)
    curriculum.initialize(db)


def library(db, token):
    row = db.execute('SELECT id FROM learning_libraries WHERE token_hash=?',
                     (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:
        raise HTTPException(404, '学习空间不存在或恢复凭据无效。')
    return row['id']


def course(db, cid, lid):
    row = db.execute('SELECT * FROM courses WHERE id=? AND library_id=?', (cid, lid)).fetchone()
    if not row:
        raise HTTPException(404, '课程不存在或无权访问。')
    return dict(row)


def can_access_session(db, sid, token):
    return db.execute('''SELECT 1 FROM course_sessions cs JOIN learning_libraries l
        ON l.id=cs.library_id WHERE cs.session_id=? AND l.token_hash=?''',
        (sid, hashlib.sha256(token.encode()).hexdigest())).fetchone() is not None


def session_course(db, sid):
    row = db.execute('''SELECT c.id,c.title,c.description FROM course_sessions cs JOIN courses c
        ON c.id=cs.course_id AND c.library_id=cs.library_id WHERE cs.session_id=?''', (sid,)).fetchone()
    return dict(row) if row else None


def attach(db, sid, lid, cid, title):
    if cid is not None:
        course(db, cid, lid)
    existing = db.execute('SELECT library_id FROM course_sessions WHERE session_id=?', (sid,)).fetchone()
    if existing:
        if existing['library_id'] != lid:
            raise HTTPException(409, '这个小课已经归属于另一个学习空间。')
        return
    db.execute('INSERT INTO course_sessions VALUES(?,?,?,?,?)', (sid, lid, cid, title, now()))


def summaries(db, lid):
    rows = db.execute('''SELECT cs.*,s.state,s.created_at,sec.id AS section_id,
        COALESCE((SELECT MAX(e.created_at) FROM events e WHERE e.session_id=s.id),s.created_at) AS last_activity
        FROM course_sessions cs JOIN sessions s ON s.id=cs.session_id
        LEFT JOIN curriculum_sections sec ON sec.session_id=s.id AND sec.course_id=cs.course_id
        WHERE cs.library_id=? ORDER BY last_activity DESC,cs.session_id''', (lid,)).fetchall()
    result = []
    for row in rows:
        state = json.loads(row['state'])
        plan = state.get('plan') or {}
        nodes = plan.get('nodes') or []
        goal = (state.get('profile') or {}).get('goal', '')
        title = goal or row['title'] or '新的小课'
        current = next((node.get('title', '') for node in nodes if node.get('status') == 'current'), '')
        result.append(dict(id=row['session_id'], course_id=row['course_id'], section_id=row['section_id'], title=title[:100],
            created_at=row['created_at'], last_activity=row['last_activity'],
            completed=bool(state.get('completed')), working=bool((state.get('job') or {}).get('status') == 'pending'),
            confirmed_nodes=sum(node.get('status') == 'completed' for node in nodes), total_nodes=len(nodes),
            current_node=current, school_context=state.get('school_context'),has_started=any(m.get('agent') == 'student' for m in state.get('messages', []))))
    return result


def public_course(row, sessions, roadmap=None):
    lessons = [item for item in sessions if item['course_id'] == row['id']]
    return {k: row[k] for k in ('id', 'title', 'description', 'created_at', 'updated_at')} | dict(
        session_count=len(lessons), ended_count=sum(item['completed'] for item in lessons),
        section_count=len(roadmap['sections']) if roadmap else 0,
        confirmed_sections=roadmap['confirmed_sections'] if roadmap else 0,
        last_activity=lessons[0]['last_activity'] if lessons else row['updated_at'],
        latest_session=lessons[0] if lessons else None)


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=400)


class ExistingSession(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    token: str = Field(min_length=1, max_length=200)
    title: str = Field(default='', max_length=200)


class ImportSessions(BaseModel):
    sessions: list[ExistingSession] = Field(max_length=200)


class MoveSession(BaseModel):
    course_id: str | None = Field(max_length=100)


def register_routes(app, connect, lock, token_value):
    @app.post('/api/learning-library')
    def create_library():
        lid, token = str(uuid4()), secrets.token_urlsafe(32)
        with lock, connect() as db:
            db.execute('INSERT INTO learning_libraries VALUES(?,?,?)',
                       (lid, hashlib.sha256(token.encode()).hexdigest(), now()))
        return {'library_id': lid, 'token': token}

    @app.get('/api/learning-library')
    def get_library(token=Depends(token_value)):
        with lock, connect() as db:
            lid = library(db, token)
            sessions = summaries(db, lid)
            rows = db.execute('SELECT * FROM courses WHERE library_id=?', (lid,)).fetchall()
            items = sorted((public_course(row, sessions,curriculum.snapshot(db,row['id'],sessions)) for row in rows), key=lambda item: item['last_activity'], reverse=True)
            return {'courses': items, 'unassigned_sessions': [item for item in sessions if item['course_id'] is None]}

    @app.post('/api/learning-library/import')
    def import_sessions(body: ImportSessions, token=Depends(token_value)):
        imported, rejected = [], []
        with lock, connect() as db:
            lid = library(db, token)
            for item in body.sessions:
                existing = db.execute('SELECT library_id FROM course_sessions WHERE session_id=?', (item.session_id,)).fetchone()
                if existing:
                    (imported if existing['library_id'] == lid else rejected).append(item.session_id)
                    continue
                row = db.execute('SELECT token_hash,state FROM sessions WHERE id=?', (item.session_id,)).fetchone()
                if not row or not secrets.compare_digest(row['token_hash'], hashlib.sha256(item.token.encode()).hexdigest()) or json.loads(row['state']).get('mode') != 'chat':
                    rejected.append(item.session_id)
                    continue
                attach(db, item.session_id, lid, None, item.title.strip())
                imported.append(item.session_id)
        return {'imported': imported, 'rejected': rejected}

    @app.post('/api/courses')
    def create_course(body: CourseInput, token=Depends(token_value)):
        title = body.title.strip()
        if not title:
            raise HTTPException(422, '请填写课程名称。')
        cid, timestamp = str(uuid4()), now()
        with lock, connect() as db:
            lid = library(db, token)
            db.execute('INSERT INTO courses VALUES(?,?,?,?,?,?)',
                       (cid, lid, title, body.description.strip(), timestamp, timestamp))
            return public_course(course(db, cid, lid), [])

    @app.patch('/api/courses/{cid}')
    def edit_course(cid: str, body: CourseInput, token=Depends(token_value)):
        title = body.title.strip()
        if not title:
            raise HTTPException(422, '请填写课程名称。')
        with lock, connect() as db:
            lid = library(db, token)
            original=course(db,cid,lid)
            lessons=[item for item in summaries(db,lid) if item['course_id']==cid]
            roadmap=db.execute('SELECT revision,plan FROM course_curricula WHERE course_id=?',(cid,)).fetchone()
            planned_titles=[s['title'] for s in json.loads(roadmap['plan'])['sections']] if roadmap and roadmap['plan'] else []
        meaningful=[item for item in lessons if item['has_started'] or item['title'] not in course_scope.EMPTY_TITLES]
        if (meaningful or planned_titles) and title!=original['title']:
            course_scope.check({'id':cid,'title':title,'description':body.description.strip()},
                '\n'.join([*(item['title'] for item in meaningful),*planned_titles]),session_id=meaningful[0]['id'] if meaningful else None,kind='rename')
        with lock, connect() as db:
            lid=library(db,token)
            if course_scope.signature(course(db,cid,lid))!=course_scope.signature(original) or [(s['id'],s['title']) for s in summaries(db,lid) if s['course_id']==cid]!=[(s['id'],s['title']) for s in lessons]:
                raise HTTPException(409,'课程或小课内容已更新，请重新提交。')
            current_roadmap=db.execute('SELECT revision FROM course_curricula WHERE course_id=?',(cid,)).fetchone()
            if (current_roadmap['revision'] if current_roadmap else 0)!=(roadmap['revision'] if roadmap else 0):
                raise HTTPException(409,'课程路线已更新，请重新提交。')
            db.execute('UPDATE courses SET title=?,description=?,updated_at=? WHERE id=?',
                       (title, body.description.strip(), now(), cid))
            return public_course(course(db, cid, lid), summaries(db, lid))

    @app.get('/api/courses/{cid}')
    def get_course(cid: str, token=Depends(token_value)):
        with lock, connect() as db:
            lid = library(db, token)
            row, sessions = course(db, cid, lid), summaries(db, lid)
            roadmap=curriculum.snapshot(db,cid,sessions)
            return {'course': public_course(row, sessions,roadmap), 'sessions': [item for item in sessions if item['course_id'] == cid],
                'curriculum':roadmap}

    @app.patch('/api/learning-library/sessions/{sid}')
    def move_session(sid: str, body: MoveSession, token=Depends(token_value)):
        with lock, connect() as db:
            lid = library(db, token)
            original=db.execute('SELECT * FROM course_sessions WHERE session_id=? AND library_id=?', (sid, lid)).fetchone()
            if not original:
                raise HTTPException(404, '小课不存在或无权访问。')
            if body.course_id!=original['course_id'] and db.execute('SELECT 1 FROM curriculum_sections WHERE session_id=?',(sid,)).fetchone():
                raise HTTPException(409,'本小课绑定课程路线中的小节，不能单独移出；可以另外创建补充小课。')
            state=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()['state'])
            destination=course(db,body.course_id,lid) if body.course_id is not None else None
        if destination and body.course_id!=original['course_id']:
            if state.get('school_context'):
                selected=state['school_context']
                course_scope.check(destination,selected['stage_label']+selected['subject_label'],session_id=sid,kind='title')
            course_scope.check(destination,course_scope.lesson_topic(state,original['title']),session_id=sid,kind='title')
        with lock, connect() as db:
            lid=library(db,token)
            fresh=db.execute('SELECT * FROM course_sessions WHERE session_id=? AND library_id=?',(sid,lid)).fetchone()
            fresh_state=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(sid,)).fetchone()['state'])
            if not fresh or fresh['course_id']!=original['course_id'] or course_scope.lesson_topic(fresh_state,fresh['title'])!=course_scope.lesson_topic(state,original['title']):
                raise HTTPException(409,'小课内容或归属已更新，请重新提交。')
            if body.course_id is not None:
                if course_scope.signature(course(db,body.course_id,lid))!=course_scope.signature(destination):
                    raise HTTPException(409,'目标课程信息已更新，请重新提交。')
            db.execute('UPDATE course_sessions SET course_id=? WHERE session_id=?', (body.course_id, sid))
        return {'session_id': sid, 'course_id': body.course_id}
