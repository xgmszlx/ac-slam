import requests,pathlib,json,concurrent.futures,subprocess
from bs4 import BeautifulSoup
R=pathlib.Path(__file__).resolve().parents[1]
jobs={'mapex':'https://arxiv.org/html/2409.15590v2','epic':'https://arxiv.org/html/2410.14203v2','falcon':'https://arxiv.org/html/2407.00577v2','graph':'https://arxiv.org/html/2308.16522v2','fael':'https://arxiv.org/pdf/2302.04658','metricsemantic':'https://docs.saurav.fyi/papers/Agarwal24_ActiveSemanticSLAM_RAL.pdf','activesplat':'https://li-yuetao.github.io/ActiveSplat/ActiveSplat.pdf'}
def f(x):
 name,url=x;j={'name':name,'url':url}
 try:
  s=requests.get(url,timeout=25);j.update(status=s.status_code,bytes=len(s.content),type=s.headers.get('Content-Type'))
  if len(s.content)>12000000:j['oversize']=True;return j
  p=R/'sources'/name;p.mkdir(exist_ok=True)
  if s.content.startswith(b'%PDF'):
   (p/'paper.pdf').write_bytes(s.content);subprocess.run(['pdftotext','-layout',str(p/'paper.pdf'),str(p/'paper.txt')],check=True);j['read_form']='PDF extracted, section anchors only'
  else:
   (p/'paper.response').write_bytes(s.content)
   if s.status_code==200 and '<title>' in s.text and ('arxiv' in url) and len(s.content)>20000:
    (p/'paper.txt').write_text(BeautifulSoup(s.text,'html.parser').get_text('\n',strip=True));j['read_form']='HTML text'
 except Exception as e:j['error']=str(e)
 return j
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rs=list(ex.map(f,jobs.items()))
(R/'audit/papers.json').write_text(json.dumps(rs,indent=2));print(json.dumps(rs,indent=2))
