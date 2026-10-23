#!/usr/bin/env python3
"""江苏省体育彩票官方排列3页面同步；仅使用真实页面记录，失败保留旧数据。"""
import json, re, sys, urllib.request, urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime, timezone, timedelta

SOURCE='https://api.js-lottery.com/wfzq/p3p5/p3data'
OUT=Path(__file__).resolve().parents[1]/'official_data.json'

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_tr=False; self.in_cell=False; self.parts=[]; self.cells=[]; self.rows=[]; self.link=None; self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='tr': self.in_tr=True; self.cells=[]
        elif tag in ('td','th') and self.in_tr: self.in_cell=True; self.parts=[]
        elif tag=='a': self.link={'href':attrs.get('href',''),'text':''}
    def handle_data(self,data):
        if self.in_cell:self.parts.append(data)
        if self.link is not None:self.link['text']+=data
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.in_cell:
            self.cells.append(' '.join(''.join(self.parts).split())); self.in_cell=False
        elif tag=='tr' and self.in_tr:
            if self.cells:self.rows.append(self.cells[:])
            self.in_tr=False
        elif tag=='a' and self.link is not None:
            self.links.append(self.link);self.link=None

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'PL3HistoricalDataSync/1.0 (GitHub Actions)','Accept':'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req,timeout=25) as r:
        final=r.geturl()
        if urllib.parse.urlparse(final).hostname != 'api.js-lottery.com':raise ValueError('跳转离开官方数据域名')
        raw=r.read(2_500_000)
        ctype=r.headers.get_content_charset() or 'utf-8'
    p=Parser();p.feed(raw.decode(ctype,errors='replace'))
    return p

def extract(p):
    found={}
    for cells in p.rows:
        if len(cells)<3:continue
        date,issue,number=cells[:3]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):continue
        if not re.fullmatch(r'\d{5,12}',issue):continue
        nums=re.findall(r'\d',number)
        if len(nums)!=3 or re.sub(r'[\d\s]','',number):continue
        try: dt=datetime.strptime(date,'%Y-%m-%d').date()
        except ValueError:continue
        if dt>datetime.now(timezone(timedelta(hours=8))).date():raise ValueError('官方返回未来日期')
        r={'issue':issue,'date':date,'num':''.join(nums)}
        if issue in found and found[issue]!=r:raise ValueError('同一期号出现冲突')
        found[issue]=r
    return found

def main():
    page=fetch(SOURCE);records=extract(page)
    if len(records)<5:raise RuntimeError(f'官方网页解析到{len(records)}条记录，不更新')
    # 尝试页面上明确指向本网站同一历史开奖栏目、文字为页码的分页链接；不猜测接口参数。
    targets=[]
    for link in page.links:
        if not re.fullmatch(r'\d{1,3}',link['text'].strip()):continue
        u=urllib.parse.urljoin(SOURCE,link['href'])
        pu=urllib.parse.urlparse(u)
        if pu.hostname=='api.js-lottery.com' and pu.path=='/wfzq/p3p5/p3data' and u!=SOURCE and u not in targets:
            targets.append(u)
    for url in targets[:11]:
        try:
            extra=extract(fetch(url))
            for issue,r in extra.items():
                if issue in records and records[issue]!=r:raise ValueError('不同页面的官方记录冲突：'+issue)
                records[issue]=r
        except Exception as exc:
            print('分页读取未成功，保留已获取记录：',type(exc).__name__,str(exc),file=sys.stderr)
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding='utf-8'))
        except Exception as exc:raise RuntimeError('旧数据损坏，拒绝覆盖') from exc
        if old.get('game')!='中国体育彩票排列3' or not isinstance(old.get('draws'),list):raise RuntimeError('旧数据格式不符')
        for r in old['draws']:
            if not (isinstance(r,dict) and re.fullmatch(r'\d{5,12}',str(r.get('issue',''))) and re.fullmatch(r'\d{3}',str(r.get('num','')))):raise RuntimeError('旧记录格式不符')
            key=str(r['issue'])
            if key in records and records[key]['num']!=str(r['num']):raise RuntimeError('新旧官方号码冲突：'+key)
            if key not in records:records[key]={'issue':key,'num':str(r['num']),'date':str(r.get('date',''))}
    rows=sorted(records.values(),key=lambda x:int(x['issue']),reverse=True)[:100]
    result={'game':'中国体育彩票排列3','source':SOURCE,'updatedAt':datetime.now(timezone.utc).isoformat(),'count':len(rows),'draws':rows}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('江苏体彩官网成功取得，累计保留',len(rows),'期，最新',rows[0]['issue'],rows[0]['num'])
    if len(rows)<30:print('警告：少于30期，不能进行30/50/100期完整窗口统计')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('同步失败，旧数据未覆盖：',type(e).__name__,e,file=sys.stderr);sys.exit(1)
