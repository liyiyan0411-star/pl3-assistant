#!/usr/bin/env python3
"""Fetch official Sporttery PL3 draw history; fail closed, never invent data."""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL='https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=35&provinceId=0&pageSize=100&isVerify=1&pageNo={}'
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36','Accept':'application/json','Referer':'https://m.lottery.gov.cn/'}
OUT=Path(__file__).resolve().parents[1]/'official_data.json'

def find_records(obj):
    out=[]
    def walk(x):
        if isinstance(x,dict):
            if 'lotteryDrawNum' in x and 'lotteryDrawResult' in x: out.append(x)
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(obj)
    return out

def fetch(page):
    req=urllib.request.Request(URL.format(page),headers=HEADERS)
    with urllib.request.urlopen(req,timeout=25) as res:
        body=res.read(4_000_000)
    return json.loads(body.decode('utf-8-sig'))

def main():
    results={}
    for page in (1,2):
        raw=fetch(page)
        records=find_records(raw)
        if not records: raise RuntimeError(f'官方接口第{page}页未返回可识别的开奖列表')
        for r in records:
            issue=str(r['lotteryDrawNum']).strip()
            nums=re.findall(r'\d+',str(r['lotteryDrawResult']))
            if len(nums)!=3 or any(len(n)!=1 for n in nums): continue
            if not re.fullmatch(r'\d{5,12}',issue): continue
            number=''.join(nums)
            date=str(r.get('lotteryDrawTime') or r.get('lotteryDrawDate') or '').strip()
            date=date[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}.*',date) else ''
            candidate={'issue':issue,'num':number,'date':date}
            if issue in results and results[issue]['num']!=number:
                raise RuntimeError(f'同一期号号码不一致: {issue}')
            results[issue]=candidate
    rows=sorted(results.values(),key=lambda r:int(r['issue']),reverse=True)[:100]
    if len(rows)<30: raise RuntimeError(f'有效记录只有{len(rows)}条，拒绝覆盖旧数据')
    # Avoid overwriting a newer snapshot with older or incomplete official responses.
    if OUT.exists():
        try:
            old=json.loads(OUT.read_text('utf-8'))
            oldrows=old.get('draws',[])
            if oldrows and int(rows[0]['issue'])<int(oldrows[0]['issue']):
                raise RuntimeError('远端返回期号比现有记录旧，拒绝覆盖')
            oldmap={r['issue']:r['num'] for r in oldrows}
            for r in rows:
                if r['issue'] in oldmap and oldmap[r['issue']]!=r['num']:
                    raise RuntimeError('与已保存期号开奖号码有冲突，拒绝覆盖：'+r['issue'])
        except (ValueError,KeyError,TypeError) as e:
            raise RuntimeError('现有数据损坏，拒绝覆盖') from e
    output={'game':'中国体育彩票排列3','source':'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry','updatedAt':datetime.now(timezone.utc).isoformat(),'count':len(rows),'draws':rows}
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',len(rows),'verified-format records; latest',rows[0]['issue'],rows[0]['num'])

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('同步失败，旧文件不会覆盖：',e,file=sys.stderr)
        sys.exit(1)
