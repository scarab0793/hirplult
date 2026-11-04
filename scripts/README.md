# Hírpult – automatikus frissítés

Napi négy futás (6, 10, 13 és 16 óra, angliai idő szerint), a `.github/workflows/update-news.yml` indítja.

## Lépések

1. `fetch_news.py` – 9 forrás RSS-e (a Telex a GitHub-futtatóról jelenleg 403-at ad, ilyenkor a korábbi adat marad). Eredmény: `data/news.json` (utolsó 72 óra) és `data/news-history.json`.
2. `enrich_news.py` – futásonként legfeljebb 6 történetből cikket ír a Claude API-val (`claude-haiku-5-5`). A forráscikket letölti, és csak abból dolgozik. Eredmény: `data/editorial.json` (az RSS-ből készült cikkeket 10 napig tartja meg).
3. `backfill_news.py` – a régi katalóguscikkek bővítése. **Alapból szünetel** (`HIRPULT_BACKFILL_BATCH: '0'`), mert a katalóguscikkek készek. Ha be van kapcsolva, a meglévő „Amit érdemes tudni” és „Szubjektív nézőpont” dobozokat nem írja felül.

Az oldal (`index.html`) a `data/news.json` és a `data/editorial.json` tartalmát futás közben fésüli össze.

## Egy cikk elkészülése

A modell cikket, „Amit érdemes tudni” és „Szubjektív nézőpont” dobozt, valamint rovatot ad vissza. A kód ezután ellenőrzi:

- minden szám szerepel-e a forrásban, számjeggyel és betűvel kiírva is (a vélemény sem hozhat be újat; az „egy”, „hat”, „hét” szavakat nem vizsgálja),
- minden idézet szó szerint megvan-e a forrásban és legfeljebb 12 szó,
- a szöveg nem ismétli-e szó szerint a forrást (hatszavas részletek átfedése legfeljebb 15%),
- a hossz arányos-e a forrás hosszával (nem tölt ki üres helyet),
- nincs benne HTML/markdown és nincs benne utalás mesterséges intelligenciára.

Ha valami nem stimmel, vagy a válasz nem érvényes JSON (például elírt idézőjel), a modell egyszer javíthat. Ha utána sem megy át, a cikk **nem jelenik meg**, a következő futásban még egyszer próbálkozik, azután lemond róla (`data/ai-state.json`). Olvashatatlan (fizetőfalas) forrásnál azonnal lemond, API-hívás nélkül.

„Megerősített” címkét az kap, amelyiknél legalább két különböző kiadó vagy egy hivatalos forrás szerepel, egyébként „Jelentett”.

## Beállítások (GitHub → Settings)

| Név | Hol | Mire |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Secrets and variables → Actions → **Secrets** | az API-kulcs |
| `ANTHROPIC_WORKSPACE_ID` | ugyanott, **Variables** (nem kötelező) | csak akkor kell, ha a kulcs nincs egy munkaterülethez kötve és a hívás erről szóló hibát ad |

| `HIRPULT_AI_MODEL` | ugyanott, **Variables** (nem kötelező) | a modell cseréje; üresen `claude-haiku-5-5` (például `claude-sonnet-5-5` erősebb, de drágább) |

| `HIRPULT_AI_EFFORT` | ugyanott, **Variables** (nem kötelező) | a „gondolkodás” mennyisége: `low` (alap, olcsóbb), `medium` (a modell saját alapja), `high`, `xhigh`, `max` |

Hasznos környezeti változók a szkriptekben: `HIRPULT_AI_MAX_ARTICLES` (cikk/futás, alap 6, legfeljebb 12), `HIRPULT_AI_MAX_CALLS` (API-hívás/futás, alap 16), `HIRPULT_KEEP_DAYS` (alap 10).

## Próba

`python scripts/test_hp_ai.py` – az ellenőrző szabályok és az API-kliens tesztjei (hálózat nélkül).
Más ágról indított kézi futás (Actions → Run workflow) a saját ágára commitol, a `main`-hez nem nyúl.
