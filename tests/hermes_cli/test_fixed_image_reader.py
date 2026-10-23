"""Fixed reader is one vision request, structured evidence, never an agent answer."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from hermes_cli import fixed_image_reader as reader
from hermes_cli.stream_json import StreamJsonEmitter
from hermes_state import SessionDB


def request(tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(4,4),'white').save(path)
    question='describe'
    return dict(query=question,image_path=str(path),origin=dict(invocation_id='a'*32,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        question_sha256=hashlib.sha256(question.encode()).hexdigest(),contract=reader.CONTRACT))


def test_session_origin_terminal_and_repeat_preserves_original(tmp_path,capsys):
    req=request(tmp_path);db=SessionDB(db_path=tmp_path/'state.db')
    vision=AsyncMock(return_value={'description':'synthetic chart','ocr':'ABC','uncertainty':''})
    assert asyncio.run(reader.read_once(req,vision=vision,store=db))==0
    events=[json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x['type'] for x in events]==['system','stage','result']
    terminal=events[-1]
    assert terminal['completed'] is True and terminal['session_persisted'] is True
    assert terminal['origin']==req['origin'] and terminal['vision_attempts']==1
    assert terminal['turn_exit_reason']=='evidence_complete' and terminal['capabilities']==['vision_once']
    before=db.get_messages(terminal['session_id'])
    with pytest.raises(FileExistsError):asyncio.run(reader.read_once(req,vision=vision,store=db))
    assert db.get_messages(terminal['session_id'])==before and vision.await_count==1
    db.close()


@pytest.mark.parametrize('case',['empty','shape','oversize','failure','cancel','timeout'])
def test_failed_and_cancelled_reads_have_no_partial_answer(tmp_path,capsys,case):
    req=request(tmp_path);db=SessionDB(db_path=tmp_path/'state.db')
    async def vision(*_):
        if case=='failure':raise RuntimeError('sensitive-provider-detail')
        if case=='cancel':raise asyncio.CancelledError
        if case=='timeout':raise TimeoutError
        if case=='shape':return {'answer':'partial summary'}
        return {'description':'x'*20000 if case=='oversize' else '', 'ocr':'', 'uncertainty':''}
    code=asyncio.run(reader.read_once(req,vision=vision,store=db))
    result=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert code!=0 and result['completed'] is False and result['evidence'] is None
    assert result['session_persisted'] and result['interrupted']==(case=='cancel')
    assert 'sensitive-provider-detail' not in json.dumps(result)
    db.close()


@pytest.mark.parametrize('case',['bad_image','hash','animated'])
def test_bad_input_never_calls_provider(tmp_path,capsys,case):
    req=request(tmp_path)
    if case=='bad_image':
        path=tmp_path/'image.png';path.write_bytes(b'bad');req['origin']['input_sha256']=hashlib.sha256(b'bad').hexdigest()
    elif case=='hash':req['origin']['input_sha256']='0'*64
    else:
        path=tmp_path/'animation.gif';Image.new('RGB',(2,2)).save(path);req['image_path']=str(path)
        req['origin']['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    db=SessionDB(db_path=tmp_path/'state.db');vision=AsyncMock()
    assert asyncio.run(reader.read_once(req,vision=vision,store=db))==1
    vision.assert_not_called();result=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['vision_attempts']==0
    db.close()


@pytest.mark.parametrize('status,finish,content',[
    (200,'stop','{"description":"ok","ocr":"","uncertainty":"low resolution"}'),
    (200,'length','{"description":"partial","ocr":"","uncertainty":""}'),
    (200,'stop',''),(401,'stop',''),(429,'stop',''),(500,'stop','')])
def test_actual_sdk_transport_no_retry_or_fallback(monkeypatch,status,finish,content):
    from openai import AsyncOpenAI
    from agent import auxiliary_client as aux
    from hermes_cli import config
    calls=[]
    async def handler(req):
        body=json.loads(req.content);calls.append(body)
        assert 'tools' not in body and body['model']=='fixture-vision' and body['max_tokens']==2048
        if status!=200:return httpx.Response(status,json={'error':{'message':'synthetic','type':'fixture'}})
        return httpx.Response(200,json={'id':'fixture','model':'fixture-vision','object':'chat.completion','created':1,
            'choices':[{'index':0,'finish_reason':finish,'message':{'role':'assistant','content':content}}]})
    client=AsyncOpenAI(api_key='fixture',base_url='https://fixture.invalid/v1',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(config,'load_config',lambda:{'auxiliary':{'vision':{'provider':'custom','model':'fixture-vision'}}})
    monkeypatch.setattr(aux,'resolve_vision_provider_client',lambda **kw:('custom',client,'fixture-vision'))
    if status==200 and finish=='stop' and content:
        assert asyncio.run(reader.vision_once('data:image/png;base64,AAA','question'))['description']=='ok'
    else:
        with pytest.raises(Exception):asyncio.run(reader.vision_once('data:image/png;base64,AAA','question'))
    assert len(calls)==1


def test_route_must_be_explicit_without_model_call(monkeypatch):
    from hermes_cli import config
    monkeypatch.setattr(config,'load_config',lambda:{'auxiliary':{'vision':{'provider':'auto','model':'fixture'}}})
    with pytest.raises(reader.EvidenceError,match='explicit_vision_route_required'):
        asyncio.run(reader.vision_once('unused','question'))


def test_terminal_preserves_incomplete_and_rejects_second_result(capsys):
    emitter=StreamJsonEmitter(origin={'invocation_id':'synthetic'})
    assert emitter.emit_result({'completed':False,'turn_exit_reason':'max_iterations','failure_reason':'budget','final_response':'partial'},exit_code=1)==1
    terminal=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert terminal['completed'] is False and terminal['turn_exit_reason']=='max_iterations'
    with pytest.raises(RuntimeError,match='terminal_already_emitted'):emitter.emit_result({'completed':True})


def test_request_binds_profile_home_and_complete_origin(tmp_path):
    from hermes_constants import get_hermes_home
    req=request(tmp_path)
    req['origin'].update(task_id='task',event_id='event',attempt_id='attempt',
        payload_sha256='b'*64,source_sha256='c'*64,profile_sha256='d'*64,target_profile_sha256='e'*64,
        profile_home_sha256=hashlib.sha256(str(get_hermes_home().resolve()).encode()).hexdigest())
    path=tmp_path/'req.json';path.write_text(json.dumps(req))
    assert reader.read_request(path)==req
    req['origin']['profile_home_sha256']='0'*64;path.write_text(json.dumps(req))
    with pytest.raises(reader.EvidenceError,match='home_identity'):reader.read_request(path)


def test_process_scope_reads_pinned_credentials_and_resets(tmp_path,monkeypatch,capsys):
    from hermes_constants import get_hermes_home
    from agent.secret_scope import get_secret,current_secret_scope
    home=tmp_path/'isolated-reader-home';home.mkdir()
    monkeypatch.setenv('HERMES_HOME',str(home))
    assert get_hermes_home().resolve()==home.resolve()
    with (home/'.env').open('x') as f:f.write('OPENAI_API_KEY=isolated-fixture-key\n')
    monkeypatch.setenv('OPENAI_API_KEY','wrong-shared-key')
    async def provider(*_):
        assert get_secret('OPENAI_API_KEY')=='isolated-fixture-key'
        return {'description':'fixture','ocr':'','uncertainty':''}
    monkeypatch.setattr(reader,'vision_once',provider)
    prior=current_secret_scope()
    assert asyncio.run(reader.run(request(tmp_path)))==0
    assert current_secret_scope() is prior
    assert 'isolated-fixture-key' not in capsys.readouterr().out


def test_unsupported_signal_loop_never_starts_reader(tmp_path,monkeypatch):
    provider=AsyncMock();monkeypatch.setattr(reader,'vision_once',provider)
    async def scenario():
        loop=asyncio.get_running_loop()
        def unsupported(*_):raise NotImplementedError
        monkeypatch.setattr(loop,'add_signal_handler',unsupported)
        with pytest.raises(reader.EvidenceError,match='signal_cancellation_unsupported'):
            await reader.run(request(tmp_path))
    asyncio.run(scenario());provider.assert_not_called()


@pytest.mark.parametrize('missing',['message','end'])
def test_silent_incomplete_storage_cannot_claim_persistence(tmp_path,monkeypatch,capsys,missing):
    req=request(tmp_path);db=SessionDB(db_path=tmp_path/'state.db')
    if missing=='end':monkeypatch.setattr(db,'end_session',lambda *_:None)
    else:
        original=db.append_message
        def append(sid,role,*args,**kw):
            return original(sid,role,*args,**kw) if role=='user' else 0
        monkeypatch.setattr(db,'append_message',append)
    vision=AsyncMock(return_value={'description':'fixture','ocr':'','uncertainty':''})
    assert asyncio.run(reader.read_once(req,vision=vision,store=db))==1
    terminal=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert terminal['session_persisted'] is False and terminal['completed'] is False
    assert terminal['evidence'] is None and terminal['turn_exit_reason']=='persistence_failed'
    db.close()
