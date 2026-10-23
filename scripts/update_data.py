#!/usr/bin/env python3
"""Fetch verified history of Sporttery PL3; fail closed without modifying existing data."""
import json, re, time, pathlib, urllib.request, datetime

ROOT=pathlib.Path(__file__).resolve().parents[1]
API='https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=35&provinceId=0&pageSize=100&isVerify=1&pageNo=1'
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36','Referer':'https://m.lottery.gov.cn/','Accept':'application/json, text/plain, */*'}

def candidates(node):
    found=[]
    if isinstance(node,dict):
        num=node.get('lotteryDrawNum'); val=node.get('lotteryDrawResult'); day=node.get('lotteryDrawTime') or node.get('lotteryDrawDate') or ''
        if num is not None and val is not None:
            found.append((str(num),str(val),str(day)))
        for x in node.values(): found+=candidates(x)
    elif isinstance(node,list):
        for x in node: found+=candidates(x)
    return found

def normalize(items):
    out={}
    for period,number,day in items:
        p=re.search(r'(\d{5})$',period)
        ds=re.findall(r'\d',number)
        if not p or len(ds)!=3:continue
        period=p.group(1)
        if int(period[2:])<1 or int(period[2:])>366:continue
        if period in out and out[period]['number']!=''.join(ds):raise ValueError('conflicting issue '+period)
        out[period]={'period':period,'number':''.join(ds),'date':str(day)[:10] if re.match(r'^20\d\d-\d\d-\d\d',str(day)) else ''}
    return sorted(out.values(),key=lambda x:int(x['period']),reverse=True)[:100]

rows=[]
for attempt in range(3):
    try:
        req=urllib.request.Request(API,headers=HEADERS)
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read(3_000_000).decode('utf-8','replace')
        obj=json.loads(raw)
        rows=normalize(candidates(obj))
        if len(rows)>=30:break
        raise ValueError(f'Only {len(rows)} parsed rows')
    except Exception as exc:
        print('attempt',attempt+1,repr(exc))
        if attempt<2:time.sleep(4*(attempt+1))
else:raise RuntimeError('Source unavailable; old data.json is preserved')

old_path=ROOT/'data.json'
if old_path.exists():
    try:
        old=json.loads(old_path.read_text('utf-8'))
        oldrows={i['period']:i['number'] for i in old.get('draws',[])}
        for i in rows:
            if i['period'] in oldrows and oldrows[i['period']]!=i['number']:
                raise ValueError(f"Conflicting official data for {i['period']}; review manually")
        if oldrows and int(rows[0]['period'])<max(map(int,oldrows)):
            raise ValueError('Source is older than stored data')
    except (ValueError,KeyError) as exc:raise

payload={'game':'中国体育彩票排列3','source':'中国体育彩票历史开奖接口','source_url':API.split('?')[0],'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),'draws':rows}
old=None
if old_path.exists():
    try:old=json.loads(old_path.read_text('utf-8'))
    except json.JSONDecodeError:pass
if old and old.get('draws')==rows:
    print('No new draws; preserving original fetched_at');exit(0)
old_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Saved',len(rows),'records; latest',rows[0])
