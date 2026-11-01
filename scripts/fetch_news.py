#!/usr/bin/env python3
"""Collect recent RSS/Atom headlines without AI or full-article copying."""
import datetime as dt
import email.utils
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

SOURCES = [
    ("24.hu", "https://24.hu/feed/", "24.hu"),
    ("Telex", "https://telex.hu/rss", "telex.hu"),
    ("HVG", "https://hvg.hu/rss", "hvg.hu"),
    ("444", "https://444.hu/feed", "444.hu"),
    ("Index", "https://index.hu/24ora/rss/", "index.hu"),
    ("Portfolio", "https://www.portfolio.hu/rss/all.xml", "portfolio.hu"),
    ("Origo", "https://www.origo.hu/publicapi/hu/rss/origo/articles", "origo.hu"),
    ("Népszava", "https://nepszava.hu/rss", "nepszava.hu"),
    ("Nemzeti Sport", "https://www.nemzetisport.hu/publicapi/hu/rss/nso/articles", "nemzetisport.hu"),
]
OUT = Path("data/news.json")
HISTORY = Path("data/news-history.json")
MONTHS = {1:"jan.",2:"febr.",3:"márc.",4:"ápr.",5:"máj.",6:"jún.",7:"júl.",8:"aug.",9:"szept.",10:"okt.",11:"nov.",12:"dec."}
def clean(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def clean_summary(s):
    text=clean(s)
    # WordPress RSS appends an English syndication footer to Hungarian excerpts.
    text=re.sub(r"\\s*The post\\s+.+?\\s+first appeared on\\s+.+?(?:\\s*\\.|$)", "", text, flags=re.I)
    text=re.sub(r"\\s*The post\\s+.*$", "", text, flags=re.I)
    return text.strip()
def child(node, name):
    for x in node:
        if x.tag.rsplit("}",1)[-1] == name: return x.text or ""
    return ""
def parse_date(value):
    try: return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try: return dt.datetime.fromisoformat(value.replace("Z","+00:00"))
        except (TypeError, ValueError): return None
def section(title, tags):
    v=(title+" "+tags).lower()
    for terms, cat in [
        (("gazdaság","forint","infláció","bank","adózás"),"Gazdaság"),
        (("sport","foci","labdarúg","olimpia"),"Sport"),
        (("film","színház","zene","könyv"),"Kultúra"),
        (("ukrajna","oroszország","trump","izrael","washington"),"Külföld"),
        (("kormány","parlament","miniszter","választás","politika"),"Belpolitika")]:
        if any(w in v for w in terms): return cat
    return "Közélet"
def feed_image(node):
    """Use only image URLs explicitly supplied by publisher RSS/Atom metadata."""
    candidates=[]
    for x in node.iter():
        tag=x.tag.rsplit("}",1)[-1].lower()
        attrs=x.attrib
        if tag in ("thumbnail","content") and ("url" in attrs):
            candidates.append(attrs["url"])
        elif tag=="enclosure" and attrs.get("type","").startswith("image/"):
            candidates.append(attrs.get("url",""))
        elif tag=="link" and attrs.get("rel")=="enclosure" and attrs.get("type","").startswith("image/"):
            candidates.append(attrs.get("href",""))
    # HTML image embedded in the RSS description, if explicitly provided
    for field in ("description","summary","encoded","content"):
        raw=child(node,field)
        m=re.search(r'<img[^>]+src=["\\\'](https?://[^"\\\']+)',raw,re.I)
        if m: candidates.append(unescape(m.group(1)))
    for url in candidates:
        p=urlparse(url)
        if p.scheme=="https" and p.hostname and not p.hostname.endswith(".invalid"):
            return url
    return ""

def collect(name, feed, host, now):
    req=urllib.request.Request(feed,headers={"User-Agent":"HirpultNewsBot/1.0 (+https://hirplult.info)"})
    with urllib.request.urlopen(req,timeout=20) as response:
        root=ET.fromstring(response.read(2_000_000))
    records=[]
    for node in root.iter():
        if node.tag.rsplit("}",1)[-1] not in ("item","entry"): continue
        title=clean(child(node,"title"))
        link=child(node,"link").strip()
        if not link:
            for e in node:
                if e.tag.rsplit("}",1)[-1]=="link" and e.attrib.get("href"):
                    link=e.attrib["href"];break
        hostname=(urlparse(link).hostname or "").lower()
        if hostname not in (host,"www."+host): continue
        date=parse_date(child(node,"pubDate") or child(node,"published") or child(node,"updated"))
        if date is None or not title: continue
        if date.tzinfo is None: date=date.replace(tzinfo=dt.timezone.utc)
        date=date.astimezone(dt.timezone.utc)
        age=(now-date).total_seconds()
        if age < -3600 or age > 72*3600: continue
        summary=clean_summary(child(node,"description") or child(node,"summary") or child(node,"content"))[:380]
        if len(summary)<25: summary=title
        tags=" ".join(clean(x.text) for x in node if x.tag.rsplit("}",1)[-1]=="category")
        image=feed_image(node)
        records.append({"id":"rss-"+hashlib.sha256(link.encode()).hexdigest()[:18],
          "r":section(title,tags),"c":name,"w":"","st":"Jelentett",
          "time":f"{MONTHS[date.month]} {date.day}.","published_at":date.isoformat(),
          "t":title,"s":summary,"p":[summary],
          "cav":"Automatikusan átvett RSS-ajánló, egyetlen forrás alapján. Részletek az eredeti cikkben.",
          "op":"","src":[[name,link]],"img":image,"imgs":name if image else "","imgl":link if image else "","cred":("Kép: "+name+" – eredeti cikk") if image else ""})
    return records
def main():
    now=dt.datetime.now(dt.timezone.utc)
    existing=[]
    if OUT.exists():
        try: existing=json.loads(OUT.read_text(encoding="utf-8")).get("items",[])
        except (ValueError,OSError): pass
    gathered=[]; success=[]; failed=[]
    for name, feed, host in SOURCES:
        try:
            rows=collect(name,feed,host,now)
            if not rows: raise ValueError("no recent valid entries")
            gathered.extend(rows);success.append(name)
        except Exception as exc:
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
            gathered.extend(x for x in existing if x.get("c")==name)
    if not success:
        raise RuntimeError("All feeds failed; previous data preserved: "+"; ".join(failed))
    unique={}
    for item in gathered:
        date=parse_date(item.get("published_at"))
        if date and date.tzinfo and -3600 <= (now-date).total_seconds() <= 72*3600:
            unique[item["id"]]=item
    rows=sorted(unique.values(),key=lambda x:x["published_at"],reverse=True)[:60]
    if not rows: raise RuntimeError("No valid recent articles; previous data preserved")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    history=json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {"items":[]}
    seen={x["id"]:x for x in history["items"]}
    for x in existing+rows:
        if x.get("id","").startswith("rss-") and x["id"] not in seen:seen[x["id"]]=x
    history["items"]=list(seen.values())[-1500:]
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUT.write_text(json.dumps({"updated_at":now.isoformat(),"sources_ok":success,"sources_failed":failed,"items":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Updated {len(rows)} headlines; OK: {success}; failed: {failed}")
if __name__=="__main__": main()
