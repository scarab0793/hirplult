"""Content-based duplicate detection for Hírpult stories. No network, no AI.

Two stories are the same when their headlines and leads share enough distinctive words and
they were published within three days of each other. Hungarian words are cut to six letters,
so "bombafenyegetés" and "bombafenyegetett" count as one word, and every word is weighted by
how rare it is in the current batch of stories: "riasztották" counts for much less than
"Gripen". The score is the cosine similarity of the two weighted word lists.

The same rules serve three places: scripts/enrich_news.py (attach a new report to an article
that already exists instead of writing it again), scripts/dedupe_editorial.py (merge
duplicates that are already stored) and the tests.
"""
import datetime as dt
import math
import re
from collections import Counter
from urllib.parse import urlparse

# Measured on real data: from 0.5 up the pairs are the same event, between 0.4 and 0.5 there are
# both the same event and neighbouring developments, so the threshold stays on the safe side.
THRESHOLD = 0.5
WINDOW_HOURS = 72
STEM = 6

# A story counts as "Megerősített" with two different publishers or one official source.
OFFICIAL_HOSTS = ("mnb.hu", "kormany.hu", "parlament.hu", "ksh.hu", "police.hu", "eurostat", "europa.eu", "mti.hu")

STOP = set(
    "hogy mint után miatt szerint magyar most több egyik másik ezzel azzal között lett volt van nem már még csak "
    "meg egy két három négy öt amely amelyet amelyek akik aki ami azt ezt ennek annak lehet kell fog fogja "
    "szerinti ellen alatt előtt közben pedig vagy illetve továbbá olyan ilyen minden néhány mintegy körül szintén "
    "ezek azok ebben abban abból innen ezen azon éppen".split()
)


def stems(text):
    """Distinctive words of a text, each cut to STEM letters."""
    return [w[:STEM] for w in re.findall(r"[a-záéíóöőúüű0-9]{4,}", str(text or "").lower()) if w not in STOP]


def _counts(item):
    counts = Counter()
    for stem in stems(item.get("t", "")):
        counts[stem] += 2  # the headline says more about the event than the lead
    for stem in stems(item.get("s", "")):
        counts[stem] += 1
    return counts


def norm_url(url):
    """A source link without scheme, www, query, fragment and trailing slash, for comparing."""
    value = re.sub(r"^https?://(www\.)?", "", str(url or "").strip().lower())
    return re.split(r"[?#]", value, maxsplit=1)[0].rstrip("/")


def published(item):
    try:
        value = dt.datetime.fromisoformat(str(item.get("published_at") or ""))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


class Index:
    """Rarity-weighted word lists of a batch of stories, so two stories can be scored."""

    def __init__(self, items):
        self._pool = list(items)  # kept alive so that id() stays unique
        self._counts = {id(x): _counts(x) for x in self._pool}
        frequency = Counter()
        for counts in self._counts.values():
            frequency.update(counts.keys())
        n = len(self._pool)
        self._idf = {word: math.log((n + 1) / (seen + 0.5)) for word, seen in frequency.items()}
        self._unknown = math.log(n + 1)  # a word that is in no story of the batch is as rare as it gets
        self._vectors = {}

    def _vector(self, item):
        key = id(item)
        if key not in self._vectors:
            counts = self._counts.get(key) or _counts(item)
            weights = {w: c * self._idf.get(w, self._unknown) for w, c in counts.items()}
            norm = math.sqrt(sum(x * x for x in weights.values())) or 1.0
            self._vectors[key] = {w: x / norm for w, x in weights.items()}
        return self._vectors[key]

    def score(self, a, b):
        x, y = self._vector(a), self._vector(b)
        if len(x) > len(y):
            x, y = y, x
        return sum(v * y[w] for w, v in x.items() if w in y)


def close_in_time(a, b, hours=WINDOW_HOURS):
    ta, tb = published(a), published(b)
    if ta is None or tb is None:
        return True
    return abs((ta - tb).total_seconds()) <= hours * 3600


def same_story(index, a, b):
    return a is not b and close_in_time(a, b) and index.score(a, b) >= THRESHOLD


def clusters(index, items):
    """Group items that tell the same story (a story is joined through any one of its members)."""
    items = list(items)
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if same_story(index, items[i], items[j]):
                parent[find(j)] = find(i)
    groups = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return list(groups.values())


def keeper(group):
    """The article to keep out of a group of duplicates: written by Claude, most sources, longest, earliest."""
    def rank(x):
        when = published(x)
        return (
            not x.get("ai_edited"),
            -len(x.get("src", [])),
            -len(" ".join(x.get("p", []))),
            when.timestamp() if when else 0,
            str(x.get("id", "")),
        )
    return min(group, key=rank)


def source_status(src):
    hosts = {(urlparse(s[1]).hostname or "").removeprefix("www.") for s in src}
    official = any(o in h for h in hosts for o in OFFICIAL_HOSTS)
    return "Megerősített" if len(hosts) >= 2 or official else "Jelentett"


def merge_into(keep, others):
    """Add the sources (and a picture, if the kept article has none) of duplicate reports to an article."""
    known = {norm_url(s[1]) for s in keep.get("src", [])}
    for other in others:
        for source in other.get("src", []):
            if norm_url(source[1]) not in known:
                keep.setdefault("src", []).append([source[0], source[1]])
                known.add(norm_url(source[1]))
    keep["st"] = source_status(keep.get("src", []))
    if not keep.get("img"):
        donor = next((x for x in others if x.get("img")), None)
        if donor:
            keep.update({k: donor.get(k, "") for k in ("img", "imgs", "imgl", "cred")})
    return keep


def find_written(index, written, group):
    """An already written article that tells the same story as any report in the group, or None."""
    for article in written:
        if any(same_story(index, article, report) for report in group):
            return article
    return None


def report_url(report):
    """The article link of a plain RSS record (its first source)."""
    src = report.get("src") or []
    return norm_url(src[0][1]) if src and len(src[0]) > 1 else ""


def covered_urls(articles):
    """Every source link that a finished article already lists."""
    return {norm_url(s[1]) for x in articles if x.get("ai_edited") for s in x.get("src", []) if len(s) > 1}


def attach_reports(articles, reports):
    """Attach plain RSS reports to the finished article that tells the same story.

    Reports whose link an article already lists are skipped. Returns (number of reports attached now,
    the reports that match no article)."""
    written = [x for x in articles if x.get("ai_edited") and str(x.get("id", "")).startswith("rss-") and x.get("published_at")]
    covered = covered_urls(articles)
    todo = [r for r in reports if report_url(r) and report_url(r) not in covered]
    index = Index(written + todo)
    attached, rest = 0, []
    for report in todo:
        article = find_written(index, written, [report])
        if article is None:
            rest.append(report)
            continue
        merge_into(article, [report])
        covered.add(report_url(report))
        attached += 1
    return attached, rest
