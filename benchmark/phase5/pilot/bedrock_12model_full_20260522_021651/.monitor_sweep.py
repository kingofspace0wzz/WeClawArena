from __future__ import annotations
import json, subprocess, time
from pathlib import Path
ROOT=Path('benchmark/phase5/pilot/bedrock_12model_full_20260522_021651')
EXPECTED={'bargaining':120,'swebench_workspace':250,'travel':100}
FILES={'bargaining':'BARGAINING_STRESS_RESULTS.jsonl','swebench_workspace':'BATCH_02_standard_RESULTS.jsonl','travel':'BATCH_02_standard_RESULTS.jsonl'}
def screen_count():
    p=subprocess.run(['screen','-ls'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return sum(1 for line in p.stdout.splitlines() if 'csa12_' in line)
def rows(path):
    if not path.is_file(): return []
    out=[]
    for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
        if not line.strip(): continue
        try: out.append(json.loads(line))
        except Exception as e: out.append({'error':f'json_parse_error:{e}'})
    return out
def step_status(master, domain):
    if not master.is_file(): return None
    status=None
    for line in master.read_text(encoding='utf-8',errors='replace').splitlines():
        marker=f'end {domain} status='
        if marker in line: status=line.rsplit(marker,1)[-1].strip()
    return status
def snap(final=False):
    jobs=[]; totals={'rows':0,'errors':0,'expected':0,'complete_jobs':0,'jobs':0}
    for model_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        for domain,fname in FILES.items():
            rs=rows(model_dir/domain/fname)
            errors=sum(1 for r in rs if r.get('error'))
            st=step_status(model_dir/'master.log', domain)
            complete=len(rs)>=EXPECTED[domain] or (st is not None and st!='0')
            jobs.append({'model':model_dir.name,'domain':domain,'rows':len(rs),'expected':EXPECTED[domain],'errors':errors,'exit_status':st,'complete':complete})
            totals['rows']+=len(rs); totals['errors']+=errors; totals['expected']+=EXPECTED[domain]; totals['jobs']+=1
            totals['complete_jobs']+=int(complete)
    data={'root':str(ROOT),'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'active_csa12_sessions':screen_count(),'totals':totals,'jobs':jobs}
    (ROOT/('final_summary.json' if final else 'status.json')).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    with (ROOT/'monitor.log').open('a',encoding='utf-8') as f:
        f.write(f"{data['timestamp']} active={data['active_csa12_sessions']} rows={totals['rows']}/{totals['expected']} errors={totals['errors']} complete_jobs={totals['complete_jobs']}/{totals['jobs']}\n")
    return data
while True:
    data=snap(False)
    if data['active_csa12_sessions']==0:
        snap(True); break
    time.sleep(300)
