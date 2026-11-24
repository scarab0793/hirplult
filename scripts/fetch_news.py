#!/usr/bin/env python3
"""Collect recent RSS/Atom headlines without AI or full-article copying."""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import email.utils
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import urlparse, urljoin

SOURCES = [
    ("24.hu", "https://24.hu/feed/", "24.hu"),
    ("Telex", "https://telex.hu/rss", "telex.hu"),
    ("HVG", "https://hvg.hu/rss", "hvg.hu"),
    ("444", "https://444.hu/feed", "444.hu"),
    ("Index", "https://index.hu/24ora/rss/", "index.hu"),
    ("Portfolio", "https://www.portfolio.hu/rss/all.xml", "portfolio.hu"),
    ("Origo", "https://www.origo.hu/publicapi/hu/rss/origo/articles", "origo.hu"),
    ("Népszava", "https://nepszava.hu/rss", "nepszava.hu"),
    ("Blikk", "https://www.blikk.hu/rss", "blikk.hu"),
    ("Nemzeti Sport", "https://www.nemzetisport.hu/publicapi/hu/rss/nso/articles", "nemzetisport.hu"),
]
# Discover publisher-advertised feeds; do not assume every site has RSS.
CATALOG = [["Telex","https://telex.hu/","",""],["HVG","https://hvg.hu/","",""],["444","https://444.hu/","",""],["24.hu","https://24.hu/","",""],["Index","https://index.hu/","",""],["Origo","https://origo.hu/","",""],["Népszava","https://nepszava.hu/","",""],["Magyar Nemzet","https://magyarnemzet.hu/","",""],["Magyar Hang","https://hang.hu/","",""],["Mandiner","https://mandiner.hu/","",""],["Infostart","https://infostart.hu/","",""],["ATV","https://atv.hu/","",""],["RTL","https://rtl.hu/","",""],["Hír TV","https://hirtv.hu/","",""],["Hirado.hu","https://hirado.hu/","",""],["Blikk","https://blikk.hu/","",""],["Kontroll","https://kontroll.hu/","",""],["Válasz Online","https://valaszonline.hu/","",""],["Átlátszó","https://atlatszo.hu/","",""],["Direkt36","https://direkt36.hu/","",""],["Magyar Narancs","https://magyarnarancs.hu/","",""],["MTI","https://mti.hu/","",""],["Portfolio","https://portfolio.hu/","Gazdaság",""],["Világgazdaság","https://vg.hu/","Gazdaság",""],["Economx","https://economx.hu/","Gazdaság",""],["Forbes","https://forbes.hu/","Gazdaság",""],["Privátbankár","https://privatbankar.hu/","Gazdaság",""],["Menedzsment Fórum","https://mfor.hu/","Gazdaság",""],["Pénzcentrum","https://penzcentrum.hu/","Gazdaság",""],["G7","https://g7.hu/","Gazdaság",""],["Piac és Profit","https://piacesprofit.hu/","Gazdaság",""],["Agrárszektor","https://agrarszektor.hu/","Gazdaság",""],["Agroinform","https://agroinform.hu/","Gazdaság",""],["Nemzeti Sport","https://nemzetisport.hu/","Sport",""],["M4 Sport","https://m4sport.hu/","Sport",""],["Sportal","https://sportal.hu/","Sport",""],["Eurosport","https://eurosport.hu/","Sport",""],["Csakfoci","https://csakfoci.hu/","Sport",""],["NB1.hu","https://nb1.hu/","Sport",""],["Rangadó","https://rangado.24.hu/","Sport",""],["FociClub","https://fociclub.hu/","Sport",""],["Formula.hu","https://formula.hu/","Sport",""],["F1Világ","https://f1vilag.hu/","Sport",""],["Racingline","https://racingline.hu/","Sport",""],["RallyCafe","https://rallycafe.hu/","Sport",""],["WBASKET","https://wbasket.hu/","Sport",""],["BB1","https://bb1.hu/","Sport",""],["Handball.hu","https://handball.hu/","Sport",""],["VLV","https://vlv.hu/","Sport",""],["Jégkorongblog","https://jegkorongblog.hu/","Sport",""],["Magyar Olimpiai Bizottság","https://olimpia.hu/","Sport",""],["MLSZ","https://mlsz.hu/","Sport",""],["Qubit","https://qubit.hu/","",""],["HWSW","https://hwsw.hu/","",""],["PROHARDVER!","https://prohardver.hu/","",""],["Rakéta","https://raketa.hu/","",""],["National Geographic","https://ng.24.hu/","",""],["Csillagászat","https://csillagaszat.hu/","",""],["Űrvilág","https://urvilag.hu/","",""],["Totalcar","https://totalcar.hu/","",""],["Vezess","https://vezess.hu/","",""],["IHO","https://iho.hu/","",""],["AIRportal","https://airportal.hu/","",""],["Honvédelem","https://honvedelem.hu/","",""],["Háború Művészete","https://haborumuveszete.hu/","",""],["Rendőrség","https://police.hu/","",""],["Katasztrófavédelem","https://katasztrofavedelem.hu/","",""],["KSH","https://ksh.hu/","",""],["MNB","https://mnb.hu/","",""],["NAV","https://nav.gov.hu/","",""],["Magyar Közlöny","https://magyarkozlony.hu/","",""],["Országgyűlés","https://parlament.hu/","",""],["Ügyészség","https://ugyeszseg.hu/","",""],["Bíróságok","https://birosag.hu/","",""],["HungaroMet","https://met.hu/","",""],["Útinform","https://utinform.hu/","",""],["MÁV","https://mavcsoport.hu/","",""],["BKK","https://bkk.hu/","",""],["Nébih","https://portal.nebih.gov.hu/","",""],["bama.hu","https://bama.hu/","Megyei","Baranya"],["pecsma.hu","https://pecsma.hu/","Megyei","Baranya"],["baon.hu","https://baon.hu/","Megyei","Bács-Kiskun"],["kecsup.hu","https://kecsup.hu/","Megyei","Bács-Kiskun"],["beol.hu","https://beol.hu/","Megyei","Békés"],["behir.hu","https://behir.hu/","Megyei","Békés"],["boon.hu","https://boon.hu/","Megyei","Borsod-Abaúj-Zemplén"],["minap.hu","https://minap.hu/","Megyei","Borsod-Abaúj-Zemplén"],["delmagyar.hu","https://delmagyar.hu/","Megyei","Csongrád-Csanád"],["szegeder.hu","https://szegeder.hu/","Megyei","Csongrád-Csanád"],["feol.hu","https://feol.hu/","Megyei","Fejér"],["fmc.hu","https://fmc.hu/","Megyei","Fejér"],["kisalfold.hu","https://kisalfold.hu/","Megyei","Győr-Moson-Sopron"],["ugytudjuk.hu","https://ugytudjuk.hu/","Megyei","Győr-Moson-Sopron"],["haon.hu","https://haon.hu/","Megyei","Hajdú-Bihar"],["dehir.hu","https://dehir.hu/","Megyei","Hajdú-Bihar"],["heol.hu","https://heol.hu/","Megyei","Heves"],["egerhirek.hu","https://egerhirek.hu/","Megyei","Heves"],["szoljon.hu","https://szoljon.hu/","Megyei","Jász-Nagykun-Szolnok"],["szolnoktv.hu","https://szolnoktv.hu/","Megyei","Jász-Nagykun-Szolnok"],["kemma.hu","https://kemma.hu/","Megyei","Komárom-Esztergom"],["dorogimedence.hu","https://dorogimedence.hu/","Megyei","Komárom-Esztergom"],["nool.hu","https://nool.hu/","Megyei","Nógrád"],["3100.hu","https://3100.hu/","Megyei","Nógrád"],["pestpilis.hu","https://pestpilis.hu/","Megyei","Pest"],["budapestkornyeke.hu","https://budapestkornyeke.hu/","Megyei","Pest"],["sonline.hu","https://sonline.hu/","Megyei","Somogy"],["kaposvarmost.hu","https://kaposvarmost.hu/","Megyei","Somogy"],["szon.hu","https://szon.hu/","Megyei","Szabolcs-Szatmár-Bereg"],["nyiregyhaza.hu","https://nyiregyhaza.hu/","Megyei","Szabolcs-Szatmár-Bereg"],["teol.hu","https://teol.hu/","Megyei","Tolna"],["szekszardihirek.hu","https://szekszardihirek.hu/","Megyei","Tolna"],["vaol.hu","https://vaol.hu/","Megyei","Vas"],["nyugat.hu","https://nyugat.hu/","Megyei","Vas"],["veol.hu","https://veol.hu/","Megyei","Veszprém"],["veszpremkukac.hu","https://veszpremkukac.hu/","Megyei","Veszprém"],["zaol.hu","https://zaol.hu/","Megyei","Zala"],["kanizsaujsag.hu","https://kanizsaujsag.hu/","Megyei","Zala"],["budapest.hu","https://budapest.hu/","Megyei","Budapest"],["enbudapestem.hu","https://enbudapestem.hu/","Megyei","Budapest"]]
class FeedLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "alternate" in a.get("rel","").lower().split() and a.get("type","").lower() in ("application/rss+xml","application/atom+xml") and a.get("href"):
            self.links.append(a["href"])

def discover(home):
    req = urllib.request.Request(home, headers={"User-Agent":"HirpultNewsBot/1.0"})
    with urllib.request.urlopen(req, timeout=8) as response:
        parser = FeedLinks()
        parser.feed(response.read(500000).decode("utf-8", errors="replace"))
        base = response.geturl()
    host = urlparse(home).hostname.removeprefix("www.")
    return list(dict.fromkeys(u for href in parser.links if (u := urljoin(base, href)) and urlparse(u).scheme == "https" and (urlparse(u).hostname or "").removeprefix("www.") == host))[:3]

OUT = Path("data/news.json")
HISTORY = Path("data/news-history.json")
MONTHS = {1:"jan.",2:"febr.",3:"márc.",4:"ápr.",5:"máj.",6:"jún.",7:"júl.",8:"aug.",9:"szept.",10:"okt.",11:"nov.",12:"dec."}
def clean(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def clean_summary(s):
    text=clean(s)
    # WordPress RSS appends an English syndication footer to Hungarian excerpts.
    text=re.sub(r"\s*The post\s+.*$", "", text, flags=re.I)
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

def collect(name, feed, host, now, category="", county=""):
    req=urllib.request.Request(feed,headers={"User-Agent":"HirpultNewsBot/1.0 (+https://hirplult.info)"})
    with urllib.request.urlopen(req,timeout=10) as response:
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
        image=""  # RSS image metadata alone does not establish reuse rights.
        records.append({"id":"rss-"+hashlib.sha256(link.encode()).hexdigest()[:18],
          "r":category or section(title,tags),"m":county,"c":name,"w":"","st":"Jelentett",
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
    fixed = {host:(name,feed) for name,feed,host in SOURCES}
    def run_source(entry):
        name,home,category,county = entry
        host = urlparse(home).hostname.removeprefix("www.")
        try:
            feeds = [fixed[host][1]] if host in fixed else discover(home)
            if not feeds: raise ValueError("no advertised RSS/Atom feed")
            rows = []
            for feed in feeds:
                try: rows.extend(collect(name,feed,host,now,category,county))
                except Exception: continue
            if not rows: raise ValueError("no recent valid entries")
            return name, rows, ""
        except Exception as exc:
            return name, [x for x in existing if x.get("c")==name], f"{name}: {type(exc).__name__}: {exc}"
    with ThreadPoolExecutor(max_workers=16) as pool:
        for name, rows, error in pool.map(run_source,CATALOG):
            gathered.extend(rows)
            if error: failed.append(error)
            else: success.append(name)
    if not success:
        raise RuntimeError("All feeds failed; previous data preserved: "+"; ".join(failed))
    unique={}
    for item in gathered:
        date=parse_date(item.get("published_at"))
        if date and date.tzinfo and -3600 <= (now-date).total_seconds() <= 72*3600:
            unique[item["id"]]=item
    rows=sorted(unique.values(),key=lambda x:x["published_at"],reverse=True)[:600]
    if not rows: raise RuntimeError("No valid recent articles; previous data preserved")
    OUT.parent.mkdir(parents=True,exist_ok=True)
    history=json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {"items":[]}
    seen={x["id"]:x for x in history["items"]}
    for x in existing+rows:
        if x.get("id","").startswith("rss-") and x["id"] not in seen:seen[x["id"]]=x
    history["items"]=list(seen.values())[-5000:]
    HISTORY.write_text(json.dumps(history,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUT.write_text(json.dumps({"updated_at":now.isoformat(),"sources_ok":success,"sources_failed":failed,"items":rows},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Updated {len(rows)} headlines; OK: {success}; failed: {failed}")
if __name__=="__main__": main()
