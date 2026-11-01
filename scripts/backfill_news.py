#!/usr/bin/env python3
"""Backfill existing Hírpult stories in small, budget-controlled batches.

Only writes verified, sufficiently detailed original reporting. Preserves
existing stories when source reporting is inaccessible.
"""
import json,os,re,urllib.request,urllib.error
from pathlib import Path
from enrich_news import compose,source_text
SOURCE=Path("index.html")
DEST=Path("data/editorial.json")
def main():
 if not SOURCE.exists():
  print("No editorial source catalog; nothing to backfill")
  return
 key=os.getenv("OPENAI_API_KEY","").strip()
 if not key:
  print("No API key; backfill skipped")
  return
 html=SOURCE.read_text(encoding="utf-8")
 marker="const items="
 start=html.find(marker)
 if start<0:raise ValueError("Embedded article catalog not found")
 entries,_=json.JSONDecoder().raw_decode(html[start+len(marker):].lstrip())
 history=Path("data/news-history.json")
 if history.exists():
  entries+=json.loads(history.read_text(encoding="utf-8")).get("items",[])
 current=Path("data/news.json")
 if current.exists():
  entries+=json.loads(current.read_text(encoding="utf-8")).get("items",[])
 old=json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else {"items":[]}
 completed={x["id"] for x in old["items"]}
 entries=list({x["id"]:x for x in entries if x.get("id")}.values())
 limit=max(0,min(3,int(os.getenv("HIRPULT_BACKFILL_BATCH","2"))))
 count=0
 for item in entries:
  if count>=limit:break
  if item["id"] in completed:continue
  sources=item.get("src",[])
  if not sources:continue
  group=[]
  for name,url in sources[:4]:
   if not isinstance(url,str) or not url.startswith("https://"):continue
   group.append({"c":name,"t":item["t"],"s":item.get("s",""),"src":[[name,url]]})
  if not group:continue
  if not any(len(source_text(x["src"][0][1]))>=1200 for x in group):
   continue
  try:
   article=compose(group,key)
   paragraphs=article.get("paragraphs",[])
   if not isinstance(paragraphs,list) or len(paragraphs)<5 or sum(map(lambda p:len(str(p)),paragraphs))<1800:
    print("Skipped insufficient article:",item["id"]);continue
   new=dict(item)
   new.update(t=str(article["title"])[:180],s=str(article["lead"])[:500],
    p=[str(p) for p in paragraphs[:12]],ai_edited=True,cav="",op="")
   old["items"].append(new)
   completed.add(item["id"]);count+=1
  except (ValueError,RuntimeError,urllib.error.HTTPError) as exc:
   print("Backfill skipped:",item["id"],type(exc).__name__)
   if isinstance(exc,RuntimeError) and "HTTP" in str(exc):break
 if count:
  DEST.parent.mkdir(parents=True,exist_ok=True)
  DEST.write_text(json.dumps(old,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("Backfilled:",count,"Total:",len(old["items"]))
if __name__=="__main__":main()
