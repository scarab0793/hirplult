#!/usr/bin/env python3
"""24.hu RSS -> reviewed-format Hírpult records; no AI, no scraping full text."""
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

FEED = "https://24.hu/feed/"
OUT = Path("data/24hu.json")
MONTHS = {1:"jan.",2:"febr.",3:"márc.",4:"ápr.",5:"máj.",6:"jún.",7:"júl.",8:"aug.",9:"szept.",10:"okt.",11:"nov.",12:"dec."}
def clean(s):
    s = re.sub(r"<[^>]*>", " ", s or "")
    return re.sub(r"\\s+", " ", unescape(s)).strip()
def category(title, tags):
    v = (title+" "+tags).lower()
    for words, name in [(("gazdaság","forint","infláció","bank","adózás"),"Gazdaság"),(("sport","foci","labdarúg","olimpia"),"Sport"),(("film","színház","zene","könyv"),"Kultúra"),(("ukrajna","oroszország","trump","eu ","izrael"),"Külföld"),(("kormány","parlament","miniszter","választás","politika"),"Belpolitika")]:
        if any(w in v for w in words): return name
    return "Közélet"
def main():
    req = urllib.request.Request(FEED, headers={"User-Agent":"HirpultRSS/1.0 (+https://hirplult.info)"})
    with urllib.request.urlopen(req, timeout=25) as res:
        root = ET.fromstring(res.read(2_000_000))
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for e in root.findall(".//channel/item"):
        title = clean(e.findtext("title"))
        link = (e.findtext("link") or "").strip()
        if not title or urlparse(link).hostname not in ("24.hu","www.24.hu"): continue
        try: published = email.utils.parsedate_to_datetime(e.findtext("pubDate"))
        except (TypeError, ValueError): continue
        if published.tzinfo is None: published = published.replace(tzinfo=dt.timezone.utc)
        age = (now-published.astimezone(dt.timezone.utc)).total_seconds()
        if age < -3600 or age > 72*3600: continue
        desc = clean(e.findtext("description"))[:450]
        if len(desc)<30: continue
        tags = " ".join(x.text or "" for x in e.findall("category"))
        out.append({"id":"rss24-"+hashlib.sha256(link.encode()).hexdigest()[:16],
          "r":category(title,tags),"c":"24.hu","w":"","st":"Jelentett",
          "time":f"{MONTHS[published.month]} {published.day}.",
          "t":title,"s":desc,"p":[desc],
          "cav":"Automatikusan átvett RSS-ajánló; a részletek és a frissítések az eredeti cikkben ellenőrizhetők.",
          "op":"","src":[["24.hu",link]],"img":"","imgs":"","imgl":"","cred":""})
    out.sort(key=lambda x:x["time"], reverse=False)
    out=out[:15]
    if not out: raise RuntimeError("No recent 24.hu RSS items; keeping previous data unchanged")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"updated_at":now.isoformat(),"source":"24.hu RSS","items":out},ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    print("24.hu records:",len(out))
if __name__=="__main__": main()
