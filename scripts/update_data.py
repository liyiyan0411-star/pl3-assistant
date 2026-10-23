#!/usr/bin/env python3
"""体彩排列3：抓取近100期历史页，并核对甘肃省体彩最新期次。失败不覆盖旧数据。"""
import datetime as dt
import json
import pathlib
import re
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILE = ROOT / 'data.json'  # 前端读取这个名字；工作流也必须提交这个名字
PAGES = ['https://www.ydniu.com/open/pl3-100.html'] + [f'https://www.ydniu.com/open/pl3-100/{x}.html' for x in range(2, 5)]
VERIFY_URL = 'https://www.gstc.org.cn/wanfa/pl3_history'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; PL3HistoryChecker/1.0; +https://github.com/)','Accept': 'text/html,application/xhtml+xml'}

class Rows(HTMLParser):
    def __init__(self): super().__init__(); self.rows=[]; self.cells=[]; self.cell=None; self.inrow=False
    def handle_starttag(self, tag, attrs):
        if tag=='tr': self.inrow=True; self.cells=[]
        if self.inrow and tag in ('td','th'): self.cell=[]
    def handle_data(self, text):
        if self.cell is not None: self.cell.append(text)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.cells.append(' '.join(''.join(self.cell).split())); self.cell=None
        if tag=='tr' and self.inrow:
            self.rows.append(self.cells);self.inrow=False

def fetch(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=22) as resp:
        return resp.read(2_000_000).decode('utf-8','replace')

def parse_history(html):
    h=Rows();h.feed(html); out=[]
    for cells in h.rows:
        line=' | '.join(cells)
        match=re.search(r'\b(20\d{5})\b',line)
        date=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',line)
        if not (match and date):continue
        ix=next((i for i,c in enumerate(cells) if match.group(1) in c),-1)
        if ix<0:continue
        # 中奖号码是日期之后的第一个独立三位数或三个单字数字段，不碰试机号
        position=next((i for i,c in enumerate(cells) if date.group(1) in c),-1)
        number=None
        for c in cells[position+1:position+3]:
            digits=re.findall(r'(?<!\d)\d(?!\d)',c)
            if len(digits)==3: number=''.join(digits);break
            if re.fullmatch(r'\d{3}',c):number=c;break
        if number:
            out.append({'period':match.group(1)[2:],'date':date.group(1),'number':number})
    return out

def official_sample(html):
    # 甘肃页面含：2026-10-22 26281 983
    return {p:n for _,p,n in re.findall(r'\b(20\d\d-\d\d-\d\d)\s+(\d{5})\s+(\d{3})\b',re.sub('<[^>]+>',' ',html))}

def main():
    rows={}
    for url in PAGES:
        parsed=parse_history(fetch(url));print(url, len(parsed),'rows')
        if len(parsed)<8: raise RuntimeError('History layout changed: '+url)
        for row in parsed:
            prev=rows.get(row['period'])
            if prev and prev!=row:raise RuntimeError('Conflict in history: '+row['period'])
            rows[row['period']]=row
    new=sorted(rows.values(),key=lambda x:int(x['period']),reverse=True)[:100]
    if len(new)!=100:raise RuntimeError(f'Only {len(new)} rows; existing data retained')
    try:
        checks=official_sample(fetch(VERIFY_URL))
        print('Gansu official records:',len(checks))
        if len(checks)<10:raise RuntimeError('Official cross-check unavailable')
        overlaps=0
        for r in new:
            if r['period'] in checks:
                overlaps+=1
                if checks[r['period']]!=r['number']:raise RuntimeError('Official mismatch at '+r['period'])
        if overlaps<10:raise RuntimeError('No sufficient overlap with provincial source')
    except Exception as e:
        raise RuntimeError('Provincial verification failed; old file retained: '+str(e))
    if FILE.exists():
        old=json.loads(FILE.read_text('utf-8'))
        existing={r['period']:r['number'] for r in old.get('draws',[])}
        if existing and int(new[0]['period'])<max(map(int,existing)):
            raise RuntimeError('Downloaded source is older than saved file')
        for r in new:
            if r['period'] in existing and existing[r['period']]!=r['number']:
                raise RuntimeError('History conflict '+r['period'])
        if old.get('draws')==new:
            print('100 draws unchanged');return
    data={'game':'中国体育彩票排列3','source':'一定牛历史数据，经甘肃省体彩最新记录交叉核对','source_url':PAGES[0],'checked_against':VERIFY_URL,'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'draws':new}
    FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved 100 records, latest:',new[0])

if __name__=='__main__':main()
