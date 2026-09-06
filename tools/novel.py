#!/usr/bin/env python3
"""中文小说工作流 v1.1. Python 3.10+，标准库，无网络或模型调用。"""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERSION = 2
STATE = ['world','characters','items','threads','relationships','reader_knowledge']
HISTORY = ['events','facts']
COLLECTIONS = STATE + HISTORY
BASE = ['01_CANON/book.json','01_CANON/canon.json','07_MEMORY/initial.json']
WEIGHTS = dict(zip(['因果','动机','人物差异','节奏','信息','情绪','文笔','对话','章尾','中国语境','一致性'],[15,15,10,10,10,10,10,5,5,5,5]))
CHECKS = ['canon','timeline','knowledge','resources','foreshadow','memory_coverage','viewpoint','originality','promise','culture']
ROUNDS = ['literary','commercial','continuity','reader']
PAYLOAD = ['draft.md','brief.json','brief.md','references.json','memory.json','sources.json','preflight.json']
ARCHIVE = PAYLOAD + ['report.json']
SOURCE_PATHS = ['AGENTS.md','00_RULES/创作宪法.md','00_RULES/工作流.md','00_RULES/文风规范.md','00_RULES/质量门禁.md','00_RULES/审稿校准.md','01_CANON/book.json','01_CANON/canon.json','01_CANON/世界观.md','01_CANON/术语表.md','02_CHARACTERS/人物档案.md','02_CHARACTERS/声线与试写反馈.md','03_PLOT/总主线.md','03_PLOT/暗线与终局.md','04_TIMELINE/时间规则.md','05_VOLUMES/当前卷纲.md']


def require(ok, msg):
    if not ok: raise ValueError(msg)


def read(p): return Path(p).read_text(encoding='utf-8-sig')

def _object(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,'JSON重复键: '+k);d[k]=v
    return d


def data(p):
    return json.loads(read(p),object_pairs_hook=_object,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('非法JSON数值: '+s)))


def encoded(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def value_hash(x): return hashlib.sha256(encoded(x)).hexdigest()
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def text_ok(x): return isinstance(x,str) and bool(x.strip())
def real_int(x): return type(x) is int


def save(p, x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.tmp-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def safe_file(relative):
    require(isinstance(relative,str),'路径必须是字符串')
    p=ROOT/relative
    require(not p.is_symlink() and p.resolve().is_relative_to(ROOT.resolve()),'路径越界或符号链接')
    require(p.is_file(),'文件不存在: '+relative)
    return p


def chapters():
    folder=ROOT/'06_CHAPTERS';folder.mkdir(exist_ok=True)
    out=[]
    for p in folder.iterdir():
        if p.name.startswith('.'):continue
        require(p.is_dir() and re.fullmatch(r'\d{4}',p.name) and not p.is_symlink(),'归档目录名异常: '+p.name)
        out.append(p)
    return sorted(out)


def work(n):
    require(real_int(n) and 1<=n<=9999,'章号范围1—9999')
    return ROOT/'work'/f'{n:04d}'


def latest():
    cs=chapters()
    return data(cs[-1]/'memory.json') if cs else data(ROOT/'07_MEMORY/initial.json')


def indexed(rows,label):
    require(isinstance(rows,list),label+'必须是数组')
    out={}
    for row in rows:
        require(isinstance(row,dict),label+'条目必须是对象')
        k=row.get('id');require(text_ok(k),label+'缺ID')
        require(k not in out,label+'重复ID: '+k);out[k]=row
    return out


def integer(x,label,minimum=0):require(real_int(x) and x>=minimum,label+'必须为整数且≥'+str(minimum))


def schema(m):
    require(isinstance(m,dict) and m.get('schema_version')==VERSION,'旧版或非法记忆格式，请按升级说明处理')
    integer(m.get('chapter'),'chapter');integer(m.get('day'),'day')
    maps={k:indexed(m.get(k),k) for k in COLLECTIONS}
    all_ids=set()
    for k,rows in maps.items():
        for id,row in rows.items():
            require(id not in all_ids,'跨集合ID重复: '+id);all_ids.add(id)
            if k in HISTORY:require(text_ok(row.get('content')),'事件/事实缺content')
    for c in maps['characters'].values():
        require(all(text_ok(c.get(k)) for k in ['name','location']),'人物缺name/location')
        require(c.get('status') in ['alive','dead','unknown'],'人物status非法')
        for kn in indexed(c.get('knowledge'),'knowledge').values():
            require(text_ok(kn.get('content')),'知识缺content')
            require(kn.get('certainty') in ['known','believed','suspected','disproven'],'知识缺certainty')
    for i in maps['items'].values():
        require('owner' in i and (i['owner'] is None or i['owner'] in maps['characters']),'道具持有者不存在')
        require(text_ok(i.get('status')),'道具缺status')
    for t in maps['threads'].values():
        integer(t.get('earliest_reveal'),'伏笔最早揭晓章')
        require(text_ok(t.get('content')),'伏笔缺content')
        require(t.get('status') in ['planned','planted','reinforced','revealed','closed'],'伏笔status非法')
        if t['status'] in ['revealed','closed']:require(t['earliest_reveal']<=m['chapter'],'伏笔提前揭晓: '+t['id'])
    for r in maps['relationships'].values():
        require(isinstance(r.get('members'),list) and len(r['members'])>=2 and all(id in maps['characters'] for id in r['members']),'关系成员不存在')
    for r in maps['reader_knowledge'].values():
        require(text_ok(r.get('content')) and r.get('certainty') in ['known','believed','suspected','disproven'],'读者知识格式非法')
    return maps


def canon_check(m):
    c=data(ROOT/'01_CANON/canon.json');facts=indexed(c.get('facts'),'canon')
    entities={row['id']:row for k in STATE for row in m[k]}
    seen=set()
    for f in facts.values():
        require(f.get('level')=='LOCKED' and text_ok(f.get('source')),'canon缺锁定级别或授权来源')
        require(text_ok(f.get('subject')) and text_ok(f.get('key')) and 'value' in f,'canon字段不完整')
        pair=(f['subject'],f['key']);require(pair not in seen,'同一属性重复锁定');seen.add(pair)
        require(f['subject'] in entities,'锁定事实对象不存在: '+f['subject'])
        require(f['key'] in entities[f['subject']] and entities[f['subject']][f['key']]==f['value'],'锁定事实冲突: '+f['id'])


def baseline_hash():return digest(ROOT/'01_CANON/seal.json')
def expected_head():
    cs=chapters()
    return {'chapter':len(cs),'manifest_sha256':digest(cs[-1]/'manifest.json') if cs else baseline_hash()}


def verify(_allow_pending=False):
    cs=chapters();seal=ROOT/'01_CANON/seal.json'
    if not seal.exists():
        require(not cs and not (ROOT/'07_MEMORY/HEAD.json').exists(),'有归档或HEAD但缺基线')
        schema(data(ROOT/'07_MEMORY/initial.json'));return 0
    s=data(seal);require(s.get('schema_version')==VERSION,'旧版基线，禁止直接覆盖升级')
    require(set(s.get('files',{}))==set(BASE),'基线清单不完整')
    for path,h in s['files'].items():require(digest(safe_file(path))==h,'基线文件被改动: '+path)
    require(digest(safe_file(s['approval_record']))==s['approval_sha256'],'授权记录被改动')
    prev=data(ROOT/'07_MEMORY/initial.json');schema(prev);canon_check(prev)
    previous=baseline_hash();history_ids=set();entity_types={}
    for k in STATE:
        for r in prev[k]:entity_types[r['id']]=k
    for number,p in enumerate(cs,1):
        require(p.name==f'{number:04d}','归档章号不连续')
        manifest=data(p/'manifest.json')
        require(manifest.get('schema_version')==VERSION and manifest.get('chapter')==number,'归档版本或章号非法')
        require(manifest.get('previous')==previous and manifest.get('baseline')==baseline_hash(),'归档链断裂')
        require(set(manifest.get('files',{}))==set(ARCHIVE),'归档清单不完整')
        require(set(f.name for f in p.iterdir())==set(ARCHIVE+['manifest.json']),'归档含未登记文件')
        for name,h in manifest['files'].items():
            require(not (p/name).is_symlink() and digest(p/name)==h,'归档损坏: '+str(p/name))
        m=data(p/'memory.json');schema(m);canon_check(m)
        validate_transition(prev,m,read(p/'draft.md'),history_ids,entity_types)
        validate_bundle(p,number,previous,check_live=False)
        for k in HISTORY:history_ids.update(r['id'] for r in m[k])
        for k in STATE:
            for r in m[k]:entity_types[r['id']]=k
        prev=m;previous=digest(p/'manifest.json')
    if not _allow_pending:
        require(not (ROOT/'07_MEMORY/transaction.json').exists(),'存在未完成归档事务，请运行doctor/recover')
        require(data(ROOT/'07_MEMORY/HEAD.json')=={'chapter':len(cs),'manifest_sha256':previous},'HEAD不匹配：可能误删末章或归档中断，运行doctor')
    return len(cs)


@contextmanager
def writer_lock():
    p=ROOT/'.writer.lock';token=uuid.uuid4().hex
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump({'token':token,'pid':os.getpid(),'host':socket.gethostname(),'created':now()},f);f.flush();os.fsync(f.fileno())
        yield
    finally:
        if p.exists():
            try:
                if data(p).get('token')==token:p.unlink()
            except (ValueError,OSError):pass


def bootstrap(evidence_path):
    with writer_lock():
        require(not (ROOT/'01_CANON/seal.json').exists() and not chapters(),'已有基线或归档，禁止重建')
        b=data(ROOT/BASE[0]);require(all(text_ok(b.get(k)) for k in ['title','genre','audience','platform','premise','narrative_view']),'书籍定位尚未填写完整')
        require(b.get('status')=='approved','需记录真实用户确认，再标记approved')
        m=data(ROOT/BASE[2]);schema(m);canon_check(m)
        require(m['chapter']==0 and not m['events'] and not m['facts'],'初始章号应为0，事件账本应为空')
        e=safe_file(str(Path(evidence_path).resolve().relative_to(ROOT.resolve())))
        require(text_ok(read(e)),'缺真实用户确认记录')
        save(ROOT/'01_CANON/seal.json',{'schema_version':VERSION,'files':{p:digest(ROOT/p) for p in BASE},'approval_record':e.relative_to(ROOT).as_posix(),'approval_sha256':digest(e)})
        save(ROOT/'07_MEMORY/HEAD.json',{'chapter':0,'manifest_sha256':baseline_hash()})
    print('基线已建立。授权真实性由操作者核对。')


def start(n):
    with writer_lock():
        verify();require((ROOT/'01_CANON/seal.json').exists(),'先初始化')
        require(n==len(chapters())+1,'必须从下一章开始')
        p=work(n);require(not p.exists(),'工作目录已存在，请恢复，不覆盖');p.mkdir(parents=True)
        for name in ['brief.json','brief.md','report.json','references.json','handoff.md']:
            shutil.copyfile(ROOT/'templates'/name,p/name)
        m=latest();m['chapter']=n;m['events']=[];m['facts']=[]
        save(p/'memory.json',m);(p/'draft.md').write_text('',encoding='utf-8')
    print(p)


def source_snapshot():
    return {path:{'sha256':digest(safe_file(path)),'text':read(ROOT/path)} for path in SOURCE_PATHS}


def validate_refs(refs,at_date):
    require(isinstance(refs,list) and refs,'缺参考卡')
    indexed(refs,'references')
    for r in refs:
        require(r.get('verified') is True,'来源未核验')
        require(text_ok(r.get('url')) and re.match(r'https?://[^/\s]+',r['url']),'参考缺有效来源链接')
        require(all(text_ok(r.get(k)) for k in ['title','takeaway','application','limitations','basis','genre_match']),'参考卡不完整')
        require(r.get('kind') in ['craft','rule'],'参考kind非法')
        require(r.get('read_scope') in ['official_guide','synopsis','sample','user_provided'],'参考阅读范围非法')
        accessed=date.fromisoformat(r['accessed']);require(accessed<=at_date,'核验日期在未来')
        # 7-day cached rules were wrongly allowed to masquerade as current.
        if r['kind']=='rule':require(accessed==at_date,'平台现行规则须当日核验')
        require(r.get('use_mode') in ['fresh','verified_cache'],'参考使用模式非法')


def validate_brief(b,n):
    require(b.get('chapter')==n,'章纲章号错误')
    for k in ['goal','stakes','change','viewpoint','ending']:
        require(text_ok(b.get(k)),'章纲缺字段: '+k)
    integer(b.get('day'),'章纲day')
    require(isinstance(b.get('entity_ids'),list) and b['entity_ids'] and len(set(b['entity_ids']))==len(b['entity_ids']) and all(text_ok(x) for x in b['entity_ids']),'章纲entity_ids缺失或重复')
    require(isinstance(b.get('new_entity_ids'),list) and set(b['new_entity_ids'])<=set(b['entity_ids']),'新增实体须列入entity_ids')
    require(isinstance(b.get('forbidden_info'),list),'缺禁止披露信息列表，无则空数组')
    scenes=b.get('scenes');require(isinstance(scenes,list) and scenes,'章纲缺场景')
    for s in scenes:
        require(isinstance(s,dict) and all(text_ok(s.get(k)) for k in ['goal','obstacle','choice','change']),'场景缺目标/阻碍/选择/变化')


def preflight(n):
    with writer_lock():
        verify();require(n==len(chapters())+1,'不是下一章');p=work(n)
        b=data(p/'brief.json');validate_brief(b,n);validate_refs(data(p/'references.json'),date.today())
        prev=latest();old={r['id'] for k in STATE for r in prev[k]}
        require(set(b['entity_ids'])<=old|set(b['new_entity_ids']),'章纲包含未登记的实体ID')
        require(not set(b['new_entity_ids'])&old,'新增实体ID与已有实体冲突')
        require(b['day']>=prev['day'],'章纲当前日倒退')
        require(read(p/'brief.md')!=read(ROOT/'templates/brief.md') and text_ok(read(p/'brief.md')),'详细章纲未填写')
        save(p/'sources.json',source_snapshot())
        save(p/'preflight.json',{'chapter':n,'baseline':baseline_hash(),'previous':expected_head()['manifest_sha256'],'date':date.today().isoformat(),'inputs':{k:digest(p/k) for k in ['brief.json','brief.md','references.json','sources.json']}})
    print('预检材料已绑定。现在逐项完成语义预检，再写正文；脚本不代替阅读。')


def validate_preflight(p,n,previous,check_live):
    pre=data(p/'preflight.json');require(pre.get('chapter')==n and pre.get('baseline')==baseline_hash() and pre.get('previous')==previous,'预检基线过期')
    require(set(pre.get('inputs',{}))=={'brief.json','brief.md','references.json','sources.json'},'预检清单不完整')
    for name,h in pre['inputs'].items():require(digest(p/name)==h,'预检后材料变更: '+name)
    sources=data(p/'sources.json');require(set(sources)==set(SOURCE_PATHS),'上下文来源清单不完整')
    for path,row in sources.items():
        require(text_ok(row.get('text')) and text_ok(row.get('sha256')),'上下文来源内容缺失')
    if check_live:require(sources==source_snapshot(),'规划或规则已变更，请重做预检与审稿')
    validate_brief(data(p/'brief.json'),n)
    used_date=date.today() if check_live else date.fromisoformat(pre['date'])
    require(date.fromisoformat(pre['date'])<=date.today(),'预检日期在未来')
    validate_refs(data(p/'references.json'),used_date)


def binding(p,n,previous):
    return {'chapter':n,'baseline':baseline_hash(),'previous':previous,'inputs':{name:digest(p/name) for name in PAYLOAD}}


def prepare_review(n):
    with writer_lock():
        verify();require(n==len(chapters())+1,'不是下一章');p=work(n);previous=expected_head()['manifest_sha256']
        validate_preflight(p,n,previous,True);require(text_ok(read(p/'draft.md')),'正文为空')
        if (p/'report.json').exists():
            h=digest(p/'report.json');save(p/'review-history'/f'{h}.json',data(p/'report.json'))
        r=data(ROOT/'templates/report.json');r['binding']=binding(p,n,previous);save(p/'report.json',r)
    print('已生成与全部材料绑定的空白审稿报告。原报告保留；必须实际重审后填写。')


def quote_check(row,text,label):
    require(isinstance(row,dict) and text_ok(row.get('quote')) and row['quote'] in text,label+'缺正文中的准确证据片段')
    require(text_ok(row.get('reason')),label+'缺具体理由')


def validate_report(report,text):
    require(report.get('review_mode') in ['self_review','external_review'],'必须说明自审或外部审稿')
    for k in ROUNDS:
        row=report.get('rounds',{}).get(k,{})
        require(row.get('passed') is True,'审稿轮次未通过: '+k);quote_check(row,text,k)
    for k in CHECKS:
        row=report.get('checks',{}).get(k,{})
        require(row.get('status') in ['pass','not_applicable'],'硬门禁未通过: '+k)
        quote_check(row,text,k)
        if k in ['canon','timeline','knowledge','memory_coverage','viewpoint','originality','promise','culture']:
            require(row['status']=='pass','此门禁不可标记不适用: '+k)
    require(report.get('blockers')==[],'存在未解决阻塞项')
    require(isinstance(report.get('issues'),list),'缺问题列表')
    for issue in report['issues']:
        require(issue.get('severity') in ['P0','P1','P2'] and issue.get('status') in ['open','resolved'],'问题级别或状态非法')
        require(text_ok(issue.get('problem')),'问题描述为空')
        require(not(issue['severity'] in ['P0','P1'] and issue['status']=='open'),'P0/P1问题未解决')
        if issue['status']=='resolved':quote_check(issue,text,'问题修复')
    total=0
    for k,w in WEIGHTS.items():
        row=report.get('scores',{}).get(k,{})
        require(real_int(row.get('score')) and 0<=row['score']<=w,'评分非法: '+k);quote_check(row,text,k);total+=row['score']
        if k in ['因果','动机','一致性']:require(row['score']>=w*0.8,'关键维度不达底线: '+k)
    require(total>=90,'评分不足90: '+str(total))
    require(isinstance(report.get('weakest_scene'),dict),'缺最弱场景诊断');quote_check(report['weakest_scene'],text,'最弱场景')
    require(isinstance(report.get('residual_risks'),list),'缺剩余风险列表，无则空数组')
    return total


def evidence(row,n,text):
    require(real_int(row.get('chapter')) and row['chapter']==n,'变化项章号错误: '+row['id'])
    require(text_ok(row.get('evidence')) and row['evidence'] in text,'证据不在当前正文: '+row['id'])


def history_identity():
    ids=set();types={}
    for m in [data(ROOT/'07_MEMORY/initial.json')]+[data(p/'memory.json') for p in chapters()]:
        for k in HISTORY:ids.update(r['id'] for r in m[k])
        for k in STATE:
            for r in m[k]:types[r['id']]=k
    return ids,types


def validate_transition(prev,m,text,history_ids,entity_types):
    old=schema(prev);new=schema(m)
    require(m['chapter']==prev['chapter']+1,'记忆章号不连续');require(m['day']>=prev['day'],'当前故事日倒退')
    for k in HISTORY:
        for id,row in new[k].items():
            require(id not in history_ids and id not in entity_types,'历史ID重复或与实体冲突: '+id);evidence(row,m['chapter'],text)
            require(isinstance(row.get('entity_ids'),list) and row['entity_ids'],'账本缺关联entity_ids')
            entities={r['id'] for c in STATE for r in m[c]}
            require(set(row['entity_ids'])<=entities,'账本关联实体不存在')
    require(m['events'],'本章至少记录一个有正文依据的推进事件')
    for k in STATE:
        require(set(old[k])<=set(new[k]),'不得删除已有实体: '+k)
        for id,row in new[k].items():
            require(id not in history_ids and (id not in entity_types or entity_types[id]==k),'跨章ID复用: '+id)
            before=old[k].get(id)
            if before==row:continue
            evidence(row,m['chapter'],text)
            require(any(id in e['entity_ids'] for e in m['events']),'状态变化缺关联事件: '+id)
            if k=='characters':
                prior=indexed(before['knowledge'],'knowledge') if before else {};known=indexed(row['knowledge'],'knowledge')
                require(set(prior)<=set(known),'知识不能静默删除；遗忘/纠错须保留知识项并说明')
                for ki,kr in known.items():
                    if prior.get(ki)!=kr:
                        evidence(kr,m['chapter'],text);require(text_ok(kr.get('acquired_via')),'知识缺获得/纠错途径')
                # Revival is a semantic/world-rule question, not a universal ban.
                if before and before['status']=='dead' and row['status']=='alive':
                    require(any(e.get('kind')=='revival' and id in e['entity_ids'] for e in m['events']),'复活缺明确剧情事件及规则复核')
            if k=='threads' and before:
                require(row['earliest_reveal']==before['earliest_reveal'],'不能静默改伏笔窗口')
                if before['status'] in ['revealed','closed']:require(row['status'] in ['revealed','closed'],'已揭晓伏笔不能回退为未揭晓')


def validate_bundle(p,n,previous,check_live):
    text=read(p/'draft.md');require(text_ok(text),'正文为空')
    validate_preflight(p,n,previous,check_live)
    report=data(p/'report.json');require(report.get('binding')==binding(p,n,previous),'审稿材料哈希不匹配，请重新审稿')
    score=validate_report(report,text)
    m=data(p/'memory.json');schema(m);canon_check(m)
    require(m['chapter']==n,'记忆章号错误')
    brief=data(p/'brief.json');require(m['day']==brief['day'],'章纲与记忆的当前日不一致')
    ids={r['id'] for k in STATE for r in m[k]}
    require(set(brief['entity_ids'])<=ids,'章纲实体未进入当前状态')
    return score


def check(n,p=None,quiet=False):
    verify();require((ROOT/'01_CANON/seal.json').exists(),'未建立基线')
    require(n==len(chapters())+1,'不是下一章，禁止重复归档');p=p or work(n)
    score=validate_bundle(p,n,expected_head()['manifest_sha256'],True)
    ids,types=history_identity();validate_transition(latest(),data(p/'memory.json'),read(p/'draft.md'),ids,types)
    if not quiet:print(f'结构门禁通过；编辑评分{score}。语义真实性仍需读稿核验。')
    return p


def accept(n):
    with writer_lock():
        p=check(n);target=ROOT/'06_CHAPTERS'/f'{n:04d}';stage=None;transaction=False
        try:
            stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=target.parent))
            original={name:digest(p/name) for name in ARCHIVE}
            for name in ARCHIVE:
                require(not (p/name).is_symlink(),'禁止用符号链接归档');shutil.copyfile(p/name,stage/name)
            require(all(digest(p/name)==h and digest(stage/name)==h for name,h in original.items()),'复制时工作材料发生变化，未归档')
            check(n,p=stage,quiet=True)  # Validate exactly the bytes being published, including memory.
            previous=expected_head();manifest={'schema_version':VERSION,'chapter':n,'baseline':baseline_hash(),'previous':previous['manifest_sha256'],'files':original}
            save(stage/'manifest.json',manifest)
            journal={'chapter':n,'stage':stage.relative_to(ROOT).as_posix(),'target':target.relative_to(ROOT).as_posix(),'previous_head':previous,'manifest_sha256':digest(stage/'manifest.json')}
            save(ROOT/'07_MEMORY/transaction.json',journal);transaction=True
            require(not target.exists(),'归档目录已存在');os.rename(stage,target);stage=None
            save(ROOT/'07_MEMORY/HEAD.json',{'chapter':n,'manifest_sha256':digest(target/'manifest.json')})
            (ROOT/'07_MEMORY/transaction.json').unlink();transaction=False
        finally:
            # Once journaled, leave evidence for recover instead of deleting a partial transaction.
            if stage and stage.exists() and not transaction:shutil.rmtree(stage)
    print(f'第{n}章已完整归档；待人工终审。')


def doctor():
    info={'lock':None,'transaction':None,'stages':[p.name for p in (ROOT/'06_CHAPTERS').glob('.stage-*')]}
    for name,path in [('lock',ROOT/'.writer.lock'),('transaction',ROOT/'07_MEMORY/transaction.json')]:
        if path.exists():
            try:info[name]=data(path)
            except (ValueError,OSError):info[name]='内容损坏，请保留文件调查'
    try:info['accepted']=verify();info['health']='ok'
    except (ValueError,KeyError,TypeError,OSError) as e:info['health']=str(e)
    print(json.dumps(info,ensure_ascii=False,indent=2));return info


def unlock(token):
    p=ROOT/'.writer.lock';record=data(p)
    require(record.get('token')==token,'锁token不匹配')
    require(record.get('host')==socket.gethostname(),'锁来自其他主机，先人工确认该主机任务')
    pid=record.get('pid');integer(pid,'PID',1)
    try:os.kill(pid,0)
    except ProcessLookupError:pass
    except PermissionError:raise ValueError('无法判断进程状态，不释放锁')
    else:raise ValueError('持锁进程仍存在，不释放锁')
    require(data(p)==record,'锁发生变化');p.unlink();print('已移除经检查的失效锁；请运行recover或verify。')


def recover():
    with writer_lock():
        jpath=ROOT/'07_MEMORY/transaction.json';require(jpath.exists(),'没有归档事务；请运行doctor定位其他问题')
        j=data(jpath);n=j['chapter'];work(n)
        require(j['target']==f'06_CHAPTERS/{n:04d}' and re.fullmatch(r'06_CHAPTERS/\.stage-[\w-]+',j['stage']),'事务路径非法')
        prefix_count=verify(_allow_pending=True)
        require(prefix_count in [n-1,n],'事务章号与现存归档不匹配')
        expected_previous={'chapter':n-1,'manifest_sha256':digest(ROOT/'06_CHAPTERS'/f'{n-1:04d}'/'manifest.json') if n>1 else baseline_hash()}
        require(j['previous_head']==expected_previous,'事务前驱记录错误')
        target=ROOT/j['target'];stage=ROOT/j['stage'];candidate=target if target.exists() else stage
        require(candidate.is_dir() and not candidate.is_symlink(),'事务数据缺失，不自动重建')
        require(digest(candidate/'manifest.json')==j['manifest_sha256'],'待恢复归档校验失败')
        man=data(candidate/'manifest.json');require(man['chapter']==n and man['previous']==j['previous_head']['manifest_sha256'],'事务前驱不匹配')
        require(set(man['files'])==set(ARCHIVE),'待恢复清单不完整')
        for name,h in man['files'].items():require(not (candidate/name).is_symlink() and digest(candidate/name)==h,'待恢复文件损坏')
        require(data(ROOT/'07_MEMORY/HEAD.json') in [j['previous_head'],{'chapter':n,'manifest_sha256':j['manifest_sha256']}],'HEAD与事务不匹配')
        require(n==j['previous_head']['chapter']+1,'事务章号不连续')
        # Prefix, sealed approval, and candidate bytes must all verify before committing HEAD.
        validate_bundle(candidate,n,man['previous'],False)
        prev=data(ROOT/'06_CHAPTERS'/f'{n-1:04d}'/'memory.json') if n>1 else data(ROOT/'07_MEMORY/initial.json')
        history=set();types={}
        for m in [data(ROOT/'07_MEMORY/initial.json')]+[data(p/'memory.json') for p in chapters() if int(p.name)<n]:
            for k in HISTORY:history.update(r['id'] for r in m[k])
            for k in STATE:
                for r in m[k]:types[r['id']]=k
        validate_transition(prev,data(candidate/'memory.json'),read(candidate/'draft.md'),history,types)
        if not target.exists():os.rename(stage,target)
        save(ROOT/'07_MEMORY/HEAD.json',{'chapter':n,'manifest_sha256':j['manifest_sha256']})
        jpath.unlink();verify()
    print('事务已恢复；未重写正文或记忆。')


def all_source_records():
    for path in SOURCE_PATHS:
        yield path,read(ROOT/path)
    initial=data(ROOT/'07_MEMORY/initial.json')
    yield '07_MEMORY/initial.json',json.dumps(initial,ensure_ascii=False)
    for c in chapters():
        yield f'06_CHAPTERS/{c.name}/draft.md',read(c/'draft.md')
        m=data(c/'memory.json')
        for k in HISTORY:
            for row in m[k]:yield f'06_CHAPTERS/{c.name}/memory.json#{k}/{row["id"]}',json.dumps(row,ensure_ascii=False)
    if chapters():
        m=latest();yield f'06_CHAPTERS/{m["chapter"]:04d}/memory.json#current_state',json.dumps({k:m[k] for k in STATE},ensure_ascii=False)


def index_signature():
    return value_hash({'head':expected_head(),'sources':{p:digest(ROOT/p) for p in SOURCE_PATHS}})


def reindex():
    verify();require((ROOT/'01_CANON/seal.json').exists(),'先初始化')
    dest=ROOT/'07_MEMORY/search.sqlite';fd,tmp=tempfile.mkstemp(dir=dest.parent,suffix='.sqlite');os.close(fd)
    try:
        db=sqlite3.connect(tmp)
        try:
            db.execute('create table meta (signature text)');db.execute('insert into meta values (?)',(index_signature(),))
            db.execute('create table records (source text primary key, content text)')
            db.executemany('insert into records values (?,?)',all_source_records())
            db.commit()
        finally:
            db.close()
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print('检索索引已重建；索引可删除重建，原文和逐章账本为权威。')


def search(query,limit=30,offset=0):
    require(text_ok(query),'检索词不能为空');integer(limit,'limit',1);integer(offset,'offset')
    require(limit<=200,'limit不能超过200');verify()
    index=ROOT/'07_MEMORY/search.sqlite'
    if not index.exists():reindex()
    stale=False
    db=None
    try:
        db=sqlite3.connect(index)
        stale=db.execute('select signature from meta').fetchone()[0]!=index_signature()
    except (sqlite3.Error,TypeError,IndexError):stale=True
    finally:
        if db:db.close()
    if stale:reindex()
    db=sqlite3.connect(index)
    try:
        count=db.execute('select count(*) from records where instr(content,?)>0',(query,)).fetchone()[0]
        rows=db.execute('select source,content from records where instr(content,?)>0 order by source limit ? offset ?',(query,limit,offset)).fetchall()
    finally:
        db.close()
    output=[]
    for source,content in rows:
        at=content.find(query);output.append({'source':source,'excerpt':content[max(0,at-80):at+len(query)+200]})
    result={'total':count,'offset':offset,'next_offset':offset+len(rows) if offset+len(rows)<count else None,'results':output}
    print(json.dumps(result,ensure_ascii=False,indent=2));return result


def context(n,page_chars=12000):
    verify();integer(page_chars,'page_chars',1000);require(page_chars<=50000,'单页上限50000字符')
    p=work(n);b=data(p/'brief.json');validate_brief(b,n)
    m=latest();ids=set(b['entity_ids'])
    selected={k:[r for r in m[k] if r['id'] in ids or (k=='items' and r.get('owner') in ids) or (k=='relationships' and ids.intersection(r.get('members',[]))) or ids.intersection(r.get('entity_ids',[]))] for k in STATE}
    due=[t for t in m['threads'] if t['status'] not in ['closed','revealed'] and t['earliest_reveal']<=n+5]
    parts=['# 决策用恢复资料；含作者信息，不直接复制进正文。']
    for name in ['00_RULES/创作宪法.md','01_CANON/canon.json','03_PLOT/总主线.md','03_PLOT/暗线与终局.md','05_VOLUMES/当前卷纲.md']:
        parts += ['\n## '+name,read(ROOT/name)]
    parts+=['\n## 本章相关状态',json.dumps(selected,ensure_ascii=False,indent=2),'\n## 到达最早揭晓窗口的线索（不代表必须此时回收）',json.dumps(due,ensure_ascii=False,indent=2)]
    if chapters():parts+=['\n## 上一章全文',read(chapters()[-1]/'draft.md')]
    parts+=['\n## 本章章纲',read(p/'brief.json'),'\n## 交接',read(p/'handoff.md')]
    text='\n'.join(parts);folder=p/'context-pages';folder.mkdir(exist_ok=True)
    names=[]
    for i,start in enumerate(range(0,len(text),page_chars),1):
        name=f'page-{i:03d}.md';(folder/name).write_text(text[start:start+page_chars],encoding='utf-8');names.append(name)
    for old in folder.glob('page-*.md'):
        if old.name not in names:old.unlink()
    # All pages preserved. Character budget is not a token estimate.
    save(p/'context-index.json',{'chapter':n,'baseline':baseline_hash(),'head':expected_head(),'sources':{x:digest(ROOT/x) for x in SOURCE_PATHS},'brief_sha256':digest(p/'brief.json'),'pages':[{'path':'context-pages/'+name,'sha256':digest(folder/name)} for name in names],'characters':len(text),'entity_ids':sorted(ids)})
    lines=['# 恢复索引','以下页面按顺序读取；这是字符分页，不是token计量。']+['- context-pages/'+name for name in names]
    lines+=['根据entity_ids、别称及本章事件使用 search 继续检索历史原文。未检索到不等于不存在。','上下文来源已变时重新运行context；不要继续引用旧页。']
    (p/'context.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print(p/'context.md')


def status():
    count=verify();active=[];archived_work=[]
    for p in sorted((ROOT/'work').iterdir()):
        if p.is_dir() and p.name.isdigit():
            (archived_work if int(p.name)<=count else active).append(p.name)
    print(json.dumps({'version':'1.1','initialized':(ROOT/'01_CANON/seal.json').exists(),'accepted_chapters':count,'next_chapter':count+1,'active_work':active,'archived_work':archived_work,'writer_lock':(ROOT/'.writer.lock').exists()},ensure_ascii=False))


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='cmd',required=True)
    for cmd in ['status','verify','doctor','recover','reindex']:sub.add_parser(cmd)
    sub.add_parser('bootstrap').add_argument('--evidence',required=True)
    for cmd in ['start','preflight','prepare-review','check','accept']:sub.add_parser(cmd).add_argument('chapter',type=int)
    c=sub.add_parser('context');c.add_argument('chapter',type=int);c.add_argument('--page-chars',type=int,default=12000)
    s=sub.add_parser('search');s.add_argument('query');s.add_argument('--limit',type=int,default=30);s.add_argument('--offset',type=int,default=0)
    sub.add_parser('hash').add_argument('path');sub.add_parser('unlock').add_argument('--token',required=True)
    a=ap.parse_args()
    try:
        if a.cmd=='verify':print('完整校验通过，正式章节数 '+str(verify()))
        elif a.cmd=='bootstrap':bootstrap(a.evidence)
        elif a.cmd in ['start','preflight','prepare-review','check','accept']:globals()[a.cmd.replace('-','_')](a.chapter)
        elif a.cmd=='context':context(a.chapter,a.page_chars)
        elif a.cmd=='search':search(a.query,a.limit,a.offset)
        elif a.cmd=='hash':print(digest(a.path))
        elif a.cmd=='unlock':unlock(a.token)
        else:globals()[a.cmd]()
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as e:
        print('阻止执行: '+str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
