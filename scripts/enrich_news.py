#!/usr/bin/env python3
"""Optional, limited AI rewriting of matching RSS reports."""
import json, os, re, hashlib, urllib.request, urllib.error
from html.parser import HTMLParser
from html import unescape
from pathlib import Path
P=Path("data/news.json")
STOP=set("hogy mint után miatt szerint magyar most több egyik másik ezzel azzal között".split())
def words(s):
 return {w for w in re.findall(r"[a-záéíóöőúüű0-9]{4,}",s.lower()) if w not in STOP}
def similar(a,b):
 x,y=words(a["t"]),words(b["t"])
 return bool(x and y and len(x&y)>=3 and len(x&y)/min(len(x),len(y))>=.65)
class ArticleParser(HTMLParser):
 def __init__(self):
  super().__init__();self.depth=0;self.ignore=0;self.parts=[];self.buffer=[];self.capture=0
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ('script','style','nav','footer','aside','header','form','svg'):
   self.ignore+=1
  if tag=='article':self.depth+=1
  if tag=='p' and not self.ignore:
   self.capture+=1;self.buffer=[]
 def handle_data(self,data):
  if self.capture and not self.ignore:self.buffer.append(data)
 def handle_endtag(self,tag):
  if tag=='p' and self.capture:
   value=' '.join(''.join(self.buffer).split())
   if len(value)>75 and len(value)<2500:self.parts.append(value)
   self.capture=0;self.buffer=[]
  if tag=='article' and self.depth:self.depth-=1
  if tag in ('script','style','nav','footer','aside','header','form','svg') and self.ignore:self.ignore-=1
def source_text(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; HirpultNewsBot/1.0; +https://hirplult.info)','Accept':'text/html'})
 try:
  with urllib.request.urlopen(req,timeout=12) as response:
   if 'html' not in response.headers.get('Content-Type',''):return ''
   raw=response.read(650000).decode('utf-8','replace')
  parser=ArticleParser();parser.feed(raw)
  parts=parser.parts
  # Only use accessible editorial paragraphs as factual reference, never republish them.
  return '\\n'.join(parts[:28])[:9500] if len(parts)>=4 else ''
 except (OSError,ValueError,UnicodeError):
  return ''
def compose(group,key):
 evidence=[{"source":x["c"],"title":x["t"],"summary":x["s"][:450],"article_reference":source_text(x["src"][0][1])} for x in group]
 if not any(len(x["article_reference"])>=1200 for x in evidence):
  raise ValueError("Insufficient full-source text for a substantial article")
 instruction=("Write an original factual Hungarian news report using ONLY these RSS summaries. "
 "Use the accessible article_reference passages as evidence, not as text to copy. "
 "Write a substantial news article of 450-700 Hungarian words in 6-9 informative paragraphs ONLY if supported by evidence. "
 "Never invent facts, quotes, details, or background. Distinguish uncertain claims. "
 "Do not copy the original wording, sentence structures, or distinctive phrases. When evidence is thin, do not generate an article. "
 "Return a JSON object with title, lead, paragraphs (array of strings). "
 "Do not add sources to the text. Evidence: "+json.dumps(evidence,ensure_ascii=False))
 body={"model":os.getenv("HIRPULT_AI_MODEL","gpt-4.1-mini"),
 "messages":[{"role":"user","content":instruction}],"temperature":0.2,
 "response_format":{"type":"json_object"}}
 req=urllib.request.Request("https://api.openai.com/v1/chat/completions",
 data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,
 "Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=45) as response:
   output=json.load(response)
 except urllib.error.HTTPError as exc:
  try:
   details=json.loads(exc.read(4096).decode('utf-8','replace'))
   info=details.get('error',{})
   code=str(info.get('code') or info.get('type') or 'unknown')
  except (ValueError,AttributeError):
   code='unknown'
  # Do not print response bodies, request headers or credentials.
  raise RuntimeError('OpenAI API HTTP '+str(exc.code)+'; error code: '+re.sub(r'[^a-zA-Z0-9_-]','',code)[:80]) from None
 return json.loads(output["choices"][0]["message"]["content"])
def main():
 key=os.getenv("OPENAI_API_KEY","").strip()
 if not key:
  print("No API key: RSS collection continues without AI.")
  return
 data=json.loads(P.read_text(encoding="utf-8"))
 rows=data.get("items",[])
 used=set();result=[];count=0
 limit=max(0,min(5,int(os.getenv("HIRPULT_AI_MAX_ARTICLES","3"))))
 for a in rows:
  if a["id"] in used:continue
  group=[a];used.add(a["id"])
  for b in rows:
   if b["id"] not in used and b["c"]!=a["c"] and similar(a,b):
    group.append(b);used.add(b["id"])
  if len(group)<2 or count>=limit:
   result.extend(group);continue
  try:
   article=compose(group,key)
   paragraphs=article.get("paragraphs",[])
   if not article.get("title") or not article.get("lead") or not isinstance(paragraphs,list) or len(paragraphs)<5 or sum(len(str(p)) for p in paragraphs)<1800:
    raise ValueError("Incomplete generated report")
   merged=dict(a)
   merged.update(id="merged-"+hashlib.sha256("|".join(sorted(x["id"] for x in group)).encode()).hexdigest()[:18],
    t=str(article["title"])[:180],s=str(article["lead"])[:500],
    p=[str(p) for p in paragraphs[:12]],c="Hírpult",
    src=[[x["c"],x["src"][0][1]] for x in group],cav="",op="",ai_edited=True)
   result.append(merged);count+=1
  except Exception as exc:
   print('AI report failed:',str(exc)[:180])
   result.extend(group)
   if isinstance(exc,RuntimeError) and any(x in str(exc) for x in ('HTTP 400','HTTP 401','HTTP 402','HTTP 403','HTTP 404','HTTP 429')):
    print('Stopping AI calls for this run; check API billing, project permissions, model access and quota.')
    result.extend(x for x in rows if x['id'] not in used)
    break
 if count:
  data["items"]=sorted(result,key=lambda x:x.get("published_at",""),reverse=True)
  P.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Generated reports:",count)
if __name__=="__main__":main()
