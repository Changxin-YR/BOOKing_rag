"""运行：python tests/scale_check.py。60章合成数据，只验证结构，不评价文学。"""
import json
import time
from test_workflow import WorkflowTests,n

case=WorkflowTests();case.setUp();started=time.perf_counter()
try:
    n.accept(1)
    for ch in range(2,61):case.prepare(ch);n.accept(ch)
    records=sum(len(n.data(p/'memory.json')['events']) for p in n.chapters())
    verified=n.verify();n.reindex();hits=n.search('E1',limit=200)
    result={'simulated_chapters':60,'verified_chapters':verified,'stored_events':records,
            'previous_design_repeated_records':sum(range(1,61)),
            'chapter1_retrievable':any(r['source'].endswith('#events/E1') for r in hits['results']),
            'elapsed_seconds':round(time.perf_counter()-started,3)}
finally:case.tearDown()
print(json.dumps(result,ensure_ascii=False,indent=2))
