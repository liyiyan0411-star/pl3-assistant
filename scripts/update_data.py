#!/usr/bin/env python3
"""体彩排列3历史数据采集：获取100期并尽可能交叉验证地方体彩。"""
import datetime as dt
import json
import pathlib
import re
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
FILE = ROOT / 'data.json'
PAGES = ['https://www.ydniu.com/open/pl3-100.html'] + [f'https://www.ydniu.com/open/pl3-100/{i}.html' for i in range(2, 5)]
VERIFY_URL = 'https://www.gstc.org.cn/wanfa/pl3_history'
HEADERS = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36', 'Accept':'text/html,application/xhtml+xml'}

class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.cells=[]; self.cell=None; self.in_row=False
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.in_row=True; self.cells=[]
        if self.in_row and tag in ('td','th'): self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.cells.append(' '.join(''.join(self.cell).split())); self.cell=None
        if tag=='tr' and self.in_row:
            self.rows.append(self.cells); self.in_row=False

class VisibleText(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag in ('tr','td','th','li','br','p','div'): self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag in ('tr','td','th','li','p','div'): self.parts.append(' ')
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)
    def get_text(self): return ' '.join(' '.join(self.parts).split())

def fetch(url):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=25) as resp:
        raw=resp.read(3_000_000)
        charset=resp.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset,'replace')

def history_rows(html):
    p=TableRows(); p.feed(html); result=[]
    for cells in p.rows:
        if len(cells)<3: continue
        period_match=re.search(r'\b(20\d{5})\b', cells[0]); date_match=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',cells[1])
        if not (period_match and date_match): continue
        # Only the winning-number column is used; trial numbers are excluded.
        digits=re.findall(r'(?<!\d)\d(?!\d)',cells[2])
        number=''.join(digits) if len(digits)==3 else cells[2].strip()
        if not re.fullmatch(r'\d{3}',number):continue
        result.append({'period':period_match.group(1)[2:],'date':date_match.group(1),'number':number})
    return result

def provincial_sample(html):
    p=VisibleText(); p.feed(html); text=p.get_text()
    # Matches date, 5-digit issue, three separate digits or an adjacent three-digit number.
    matches=re.findall(r'\b(20\d{2}-\d{2}-\d{2})\s+(\d{5})\s+(\d(?:\s*\d){2})\b',text)
    return {period:re.sub(r'\s+','',num) for date,period,num in matches}

def main():
    by_period={}
    for url in PAGES:
        parsed=history_rows(fetch(url))
        print('History source',url,'parsed',len(parsed))
        if len(parsed)<8: raise RuntimeError('History page unavailable or format changed: '+url)
        for r in parsed:
            old=by_period.get(r['period'])
            if old and old!=r: raise RuntimeError('Conflicting historical data at '+r['period'])
            by_period[r['period']]=r
    recent=sorted(by_period.values(),key=lambda r:int(r['period']),reverse=True)[:100]
    if len(recent)!=100: raise RuntimeError('Only '+str(len(recent))+' rows; existing file untouched')
    if len({r['period'] for r in recent})!=100: raise RuntimeError('Duplicated issue numbers')
    for r in recent:
        if not re.fullmatch(r'\d{5}',r['period']) or not re.fullmatch(r'\d{3}',r['number']):
            raise RuntimeError('Invalid issue or number')
        dt.date.fromisoformat(r['date'])

    verified_count=0; verification_note='地方体彩核验不可用；历史数据尚未经官方交叉核验'
    try:
        checks=provincial_sample(fetch(VERIFY_URL))
        print('Provincial records parsed:',len(checks))
        for r in recent:
            if r['period'] in checks:
                if checks[r['period']]!=r['number']:raise RuntimeError('Official mismatch: '+r['period'])
                verified_count+=1
        if verified_count>=10:
            verification_note=f'甘肃省体彩网交叉核验{verified_count}期一致'
        else:
            verification_note=f'仅核验{verified_count}期，不满足10期核验门槛'
    except Exception as e:
        if 'Official mismatch' in str(e): raise  # conflicting numbers must stop the update
        print('WARNING: Provincial validation unavailable:',str(e))
    # A failure to cross-verify is clearly recorded rather than mislabeled as verified.
    if FILE.exists():
        old=json.loads(FILE.read_text('utf-8'))
        existing={str(r['period']):str(r['number']) for r in old.get('draws',[])}
        if existing and int(recent[0]['period'])<max(map(int,existing)):raise RuntimeError('Downloaded data is older than saved data')
        for r in recent:
            if r['period'] in existing and r['number']!=existing[r['period']]:raise RuntimeError('Existing-data conflict: '+r['period'])
        if old.get('draws')==recent and old.get('verification')==verification_note:
            print('No changes');return
    payload={'game':'中国体育彩票排列3','source':'一定牛历史开奖记录（第三方）','source_url':PAGES[0],
             'verification':verification_note,'verified_count':verified_count,
             'verification_url':VERIFY_URL,'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'draws':recent}
    FILE.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',len(recent),'latest',recent[0],verification_note)

if __name__=='__main__':main()
