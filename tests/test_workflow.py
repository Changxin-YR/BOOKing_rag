import importlib.util
from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('novel',BASE/'tools/novel.py');n=importlib.util.module_from_spec(spec);spec.loader.exec_module(n)
TEXT='林砚走到渡口，把家信交给船夫。船夫收下信，告诉他明早才开船。林砚只好在渡口等一夜。'
QUOTE='把家信交给船夫'

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.out=StringIO();self.redirect=redirect_stdout(self.out);self.redirect.__enter__()
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'book'
        shutil.copytree(BASE,self.root,ignore=shutil.ignore_patterns('__pycache__','search.sqlite'))
        self.old=n.ROOT;n.ROOT=self.root
        b=n.data(self.root/'01_CANON/book.json');b.update({k:'测试用构想' for k in ['title','genre','audience','platform','premise','narrative_view']});b['status']='approved';n.save(self.root/'01_CANON/book.json',b)
        m=n.data(self.root/'07_MEMORY/initial.json');m['characters']=[{'id':'C1','name':'林砚','status':'alive','location':'渡口','knowledge':[]}];m['world']=[{'id':'W1','can_revive':False}]
        n.save(self.root/'07_MEMORY/initial.json',m)
        n.save(self.root/'01_CANON/canon.json',{'facts':[{'id':'L1','subject':'C1','key':'name','value':'林砚','level':'LOCKED','source':'仅测试夹具，非真实用户批准'}]})
        self.e=self.root/'approvals/initial.md';self.e.write_text('自动化测试中的虚拟授权，不是用户小说。',encoding='utf-8')
        n.bootstrap(self.e);self.prepare(1)
    def tearDown(self):
        n.ROOT=self.old;self.tmp.cleanup();self.redirect.__exit__(None,None,None)
    def prepare(self,num):
        n.start(num);self.p=n.work(num)
        b=n.data(self.p/'brief.json');b.update(chapter=num,day=num,goal='把信送出',stakes='家人等待消息',change='从急着离开到被迫等待',viewpoint='林砚限知',ending='次日船程未知',entity_ids=['C1'],new_entity_ids=[],forbidden_info=[],scenes=[{'goal':'交信','obstacle':'船未开','choice':'留下等待','change':'停留一夜'}]);n.save(self.p/'brief.json',b)
        (self.p/'brief.md').write_text('交信后得知船期推迟，主角等待一夜。',encoding='utf-8')
        r=[{'id':'R1','url':'https://example.com/fixture','title':'测试夹具','accessed':date.today().isoformat(),'verified':True,'kind':'craft','read_scope':'official_guide','takeaway':'行动带来新限制','application':'交信后得知船期','limitations':'仅用于软件测试，未开展真实研究','basis':'测试数据','genre_match':'测试','use_mode':'verified_cache'}];n.save(self.p/'references.json',r)
        n.preflight(num);(self.p/'draft.md').write_text(TEXT,encoding='utf-8')
        m=n.data(self.p/'memory.json');m.update(chapter=num,day=num,events=[{'id':f'E{num}','content':'交信并得知开船时间','entity_ids':['C1'],'chapter':num,'evidence':QUOTE}],facts=[]);n.save(self.p/'memory.json',m)
        self.approve(num)
    def approve(self,num=1):
        n.prepare_review(num);r=n.data(self.p/'report.json');r['blockers']=[]
        for k in n.ROUNDS:r['rounds'][k]={'passed':True,'quote':QUOTE,'reason':'测试夹具：动作造成等待，非真实文学评分'}
        for k in n.CHECKS:r['checks'][k]={'status':'pass','quote':QUOTE,'reason':'测试夹具：对照原文'}
        for k,v in n.WEIGHTS.items():r['scores'][k]={'score':v,'quote':QUOTE,'reason':'仅用于检查器测试'}
        r['weakest_scene']={'quote':QUOTE,'reason':'测试夹具，不代表作品已达到质量标准'};n.save(self.p/'report.json',r)
    def edit(self,name,fn):
        x=n.data(self.p/name);fn(x);n.save(self.p/name,x)
    def expect(self,pattern=''):
        return self.assertRaisesRegex(ValueError,pattern)
    def test_accept_and_resume(self):
        n.accept(1);self.assertEqual(n.verify(),1);self.assertEqual(n.latest()['events'][0]['id'],'E1')
        self.prepare(2);n.context(2);self.assertIn('page-001',n.read(self.p/'context.md'))
        n.accept(2);self.assertEqual(n.verify(),2)
    def test_stale_draft_review(self):
        (self.p/'draft.md').write_text(TEXT+'风起了。',encoding='utf-8')
        with self.expect('审稿材料'):n.check(1)
    def test_stale_memory_review(self):
        self.edit('memory.json',lambda m:m['characters'][0].update(location='火星',chapter=1,evidence=QUOTE))
        with self.expect('审稿材料'):n.check(1)
    def test_stale_reference_review(self):
        self.edit('references.json',lambda r:r[0].update(takeaway='另一个结论'))
        with self.expect('预检后材料'):n.check(1)
    def test_stale_planning_review(self):
        (self.root/'03_PLOT/总主线.md').write_text('主线改变了',encoding='utf-8')
        with self.expect('规划或规则'):n.check(1)
    def test_stale_style_feedback(self):
        (self.root/'02_CHARACTERS/声线与试写反馈.md').write_text('改变文风',encoding='utf-8')
        with self.expect('规划或规则'):n.check(1)
    def test_false_quote(self):
        self.edit('report.json',lambda r:r['rounds']['literary'].update(quote='随便填'))
        with self.expect('证据片段'):n.check(1)
    def test_false_score_quote(self):
        self.edit('report.json',lambda r:r['scores']['因果'].update(quote='正文不存在'))
        with self.expect('证据片段'):n.check(1)
    def test_blank_reason(self):
        self.edit('report.json',lambda r:r['scores']['因果'].update(reason='  '))
        with self.expect('理由'):n.check(1)
    def test_core_dimension_floor(self):
        self.edit('report.json',lambda r:r['scores']['一致性'].update(score=0))
        with self.expect('关键维度'):n.check(1)
    def test_total_score_floor(self):
        self.edit('report.json',lambda r:r['scores']['人物差异'].update(score=0))
        self.edit('report.json',lambda r:r['scores']['章尾'].update(score=0))
        with self.expect('评分不足'):n.check(1)
    def test_open_p1_even_high_score(self):
        self.edit('report.json',lambda r:r['issues'].append({'severity':'P1','status':'open','problem':'重要动机断裂'}))
        with self.expect('P0/P1'):n.check(1)
    def test_hard_check_cannot_be_na(self):
        self.edit('report.json',lambda r:r['checks']['knowledge'].update(status='not_applicable'))
        with self.expect('不可标记'):n.check(1)
    def test_p2_allowed_and_retained(self):
        self.edit('report.json',lambda r:r['issues'].append({'severity':'P2','status':'open','problem':'轻微重复'}))
        n.accept(1);self.assertEqual(n.data(self.root/'06_CHAPTERS/0001/report.json')['issues'][0]['problem'],'轻微重复')
    def test_canon_name_conflict(self):
        self.edit('memory.json',lambda m:m['characters'][0].update(name='林研',chapter=1,evidence=QUOTE));self.approve()
        with self.expect('锁定事实'):n.check(1)
    def test_dangling_world_canon(self):
        c=n.data(self.root/'01_CANON/canon.json');c['facts'].append({'id':'L2','subject':'W404','key':'value','value':'x','source':'测试','level':'LOCKED'});n.save(self.root/'01_CANON/canon.json',c)
        with self.expect('对象不存在'):n.canon_check(n.latest())
    def test_cross_collection_duplicate(self):
        self.edit('memory.json',lambda m:m['items'].append({'id':'C1','owner':None,'status':'存在'}));self.approve()
        with self.expect('跨集合ID'):n.check(1)
    def test_nonexistent_item_owner(self):
        self.edit('memory.json',lambda m:m['items'].append({'id':'I1','owner':'ghost','status':'存在'}));self.approve()
        with self.expect('持有者'):n.check(1)
    def test_new_state_requires_event(self):
        self.edit('memory.json',lambda m:m['items'].append({'id':'I1','owner':'C1','status':'存在','chapter':1,'evidence':QUOTE}));self.approve()
        with self.expect('缺关联事件'):n.check(1)
    def test_knowledge_acquisition_required(self):
        self.edit('memory.json',lambda m:m['characters'][0].update(chapter=1,evidence=QUOTE,knowledge=[{'id':'K1','content':'船期','certainty':'known','chapter':1,'evidence':QUOTE}]))
        self.approve()
        with self.expect('获得/纠错途径'):n.check(1)
    def test_early_reveal(self):
        self.edit('memory.json',lambda m:m['threads'].append({'id':'T1','content':'秘密','earliest_reveal':10,'status':'revealed','chapter':1,'evidence':QUOTE}));self.approve()
        with self.expect('提前揭晓'):n.check(1)
    def test_future_reference_date(self):
        r=n.data(self.p/'references.json');r[0]['accessed']=(date.today()+timedelta(days=1)).isoformat()
        with self.expect('未来'):n.validate_refs(r,date.today())
    def test_rule_requires_same_day(self):
        r=n.data(self.p/'references.json');r[0].update(kind='rule',accessed=(date.today()-timedelta(days=1)).isoformat())
        with self.expect('当日'):n.validate_refs(r,date.today())
    def test_historical_craft_cache_allowed(self):
        r=n.data(self.p/'references.json');r[0]['accessed']='2020-01-01';n.validate_refs(r,date.today())
    def test_unverified_source(self):
        r=n.data(self.p/'references.json');r[0]['verified']=False
        with self.expect('未核验'):n.validate_refs(r,date.today())
    def test_empty_structural_brief(self):
        self.edit('brief.json',lambda b:b.update(goal=' '))
        with self.expect('章纲缺字段'):n.preflight(1)
    def test_approval_tamper(self):
        self.e.write_text('被替换的批准',encoding='utf-8')
        with self.expect('授权记录'):n.verify()
    def test_baseline_tamper(self):
        n.save(self.root/'01_CANON/canon.json',{'facts':[]})
        with self.expect('基线文件'):n.verify()
    def test_last_chapter_deletion(self):
        n.accept(1);shutil.rmtree(self.root/'06_CHAPTERS/0001')
        with self.expect('HEAD'):n.verify()
    def test_archive_tamper(self):
        n.accept(1);(self.root/'06_CHAPTERS/0001/memory.json').write_text('{}',encoding='utf-8')
        with self.expect('归档损坏'):n.verify()
    def test_manifest_chain(self):
        n.accept(1);x=n.data(self.root/'06_CHAPTERS/0001/manifest.json');x['previous']='wrong';n.save(self.root/'06_CHAPTERS/0001/manifest.json',x)
        with self.expect('归档链'):n.verify()
    def test_duplicate_accept(self):
        n.accept(1)
        with self.expect('下一章'):n.accept(1)
    def test_failed_check_no_archive(self):
        self.edit('report.json',lambda r:r.update(blockers=['冲突']))
        with self.expect('阻塞项'):n.accept(1)
        self.assertEqual(n.latest()['chapter'],0);self.assertFalse((self.root/'.writer.lock').exists())
    def test_concurrent_lock(self):
        (self.root/'.writer.lock').write_text('other',encoding='utf-8')
        with self.assertRaises(FileExistsError):n.accept(1)
        self.assertTrue((self.root/'.writer.lock').exists())
    def test_copy_time_memory_change(self):
        original=shutil.copyfile
        def changed(src,dst,*args,**kwargs):
            result=original(src,dst,*args,**kwargs)
            if Path(src)==self.p/'memory.json':
                self.edit('memory.json',lambda m:m.update(day=99))
            return result
        with patch.object(n.shutil,'copyfile',side_effect=changed):
            with self.expect('复制时'):n.accept(1)
        self.assertFalse((self.root/'06_CHAPTERS/0001').exists())
    def test_recover_after_rename_before_head(self):
        original=n.save
        def fail_head(path,value):
            if str(path).endswith('HEAD.json'):raise OSError('模拟进程中断')
            return original(path,value)
        with patch.object(n,'save',side_effect=fail_head):
            with self.assertRaises(OSError):n.accept(1)
        self.assertTrue((self.root/'07_MEMORY/transaction.json').exists())
        with self.expect('事务'):n.verify()
        n.recover();self.assertEqual(n.verify(),1)
    def test_recover_before_rename(self):
        with patch.object(n.os,'rename',side_effect=OSError('模拟重命名失败')):
            with self.assertRaises(OSError):n.accept(1)
        self.assertFalse((self.root/'06_CHAPTERS/0001').exists());n.recover();self.assertEqual(n.verify(),1)
    def test_recover_rejects_damaged_candidate(self):
        with patch.object(n.os,'rename',side_effect=OSError('模拟失败')):
            with self.assertRaises(OSError):n.accept(1)
        j=n.data(self.root/'07_MEMORY/transaction.json');(self.root/j['stage']/'memory.json').write_text('{}',encoding='utf-8')
        with self.expect('待恢复文件损坏'):n.recover()
        self.assertEqual(n.data(self.root/'07_MEMORY/HEAD.json')['chapter'],0)
    def test_recover_checks_approval_before_publishing(self):
        with patch.object(n.os,'rename',side_effect=OSError('模拟失败')):
            with self.assertRaises(OSError):n.accept(1)
        self.e.write_text('改授权',encoding='utf-8')
        with self.expect('授权记录'):n.recover()
        self.assertFalse((self.root/'06_CHAPTERS/0001').exists())
    def test_history_is_chapter_local(self):
        n.accept(1);self.prepare(2);n.accept(2)
        self.assertEqual([x['id'] for x in n.latest()['events']],['E2'])
        self.assertEqual([x['id'] for x in n.data(self.root/'06_CHAPTERS/0001/memory.json')['events']],['E1'])
    def test_duplicate_historical_event(self):
        n.accept(1);self.prepare(2);self.edit('memory.json',lambda m:m['events'][0].update(id='E1'));self.approve(2)
        with self.expect('历史ID重复'):n.check(2)
    def test_search_old_event_and_pagination(self):
        n.accept(1);self.prepare(2);n.accept(2)
        r=n.search('E1',limit=1);self.assertGreaterEqual(r['total'],1);self.assertIn('0001/memory',r['results'][0]['source'])
        r=n.search('林砚',limit=1);self.assertIsNotNone(r['next_offset'])
    def test_search_index_invalidation(self):
        n.accept(1);n.reindex();(self.root/'03_PLOT/总主线.md').write_text('新规划特有词',encoding='utf-8')
        r=n.search('新规划特有词');self.assertEqual(r['total'],1)
    def test_context_pages_preserve_full_text(self):
        n.accept(1);self.prepare(2);(self.root/'03_PLOT/暗线与终局.md').write_text('秘'*4500+'结束锚点',encoding='utf-8')
        n.context(2,page_chars=1000);index=n.data(self.p/'context-index.json')
        self.assertGreater(len(index['pages']),4)
        content=''.join(n.read(self.p/r['path']) for r in index['pages']);self.assertIn('结束锚点',content)
        self.assertTrue(all(len(n.read(self.p/r['path']))<=1000 for r in index['pages']))
    def test_context_includes_related_clue(self):
        self.edit('memory.json',lambda m:m['threads'].append({'id':'T9','content':'关联角色的远期线索','entity_ids':['C1'],'earliest_reveal':100,'status':'planted','chapter':1,'evidence':QUOTE}))
        self.edit('memory.json',lambda m:m['events'][0]['entity_ids'].append('T9'))
        self.approve();n.accept(1);self.prepare(2);n.context(2)
        index=n.data(self.p/'context-index.json');content=''.join(n.read(self.p/r['path']) for r in index['pages'])
        self.assertIn('关联角色的远期线索',content)
    def test_prepare_review_resets_passes(self):
        n.prepare_review(1);r=n.data(self.p/'report.json');self.assertFalse(r['rounds']['literary']['passed'])
        self.assertTrue(list((self.p/'review-history').glob('*.json')))
    def test_duplicate_json_keys(self):
        (self.p/'bad.json').write_text('{"a":1,"a":2}',encoding='utf-8')
        with self.expect('重复键'):n.data(self.p/'bad.json')
    def test_bool_not_integer(self):
        self.edit('memory.json',lambda m:m.update(day=True));self.approve()
        with self.expect('整数'):n.check(1)
    def test_no_silent_state_deletion(self):
        self.edit('memory.json',lambda m:m.update(world=[]));self.approve()
        with self.expect('删除已有实体'):n.check(1)
    def test_status_ignores_archived_work(self):
        n.accept(1);self.out.truncate(0);self.out.seek(0);n.status()
        r=json.loads(self.out.getvalue());self.assertEqual(r['active_work'],[]);self.assertEqual(r['archived_work'],['0001'])

if __name__=='__main__':unittest.main()
