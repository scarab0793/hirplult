# Hírpult – hírgyűjtés és szerkesztés

A GitHub Actions naponta négy alkalommal (6, 10, 13, 16 óra, UK idő) gyűjt RSS/Atom híreket a 119 forrásból. A sikeres és sikertelen források listája a data/news.json fájlban található. A data/news-history.json a nyers hírarchívum.

A fizetős Claude-cikkírás és backfill nincs a workflow-ban. A korábbi szkriptek megmaradnak, de automatikusan nem futnak. A duplikációszűrés továbbra is fut.

## Szerkesztőségi publikálás
- A nyers RSS nem kész cikk. Ellenőrizni kell az eredeti forrásokat, lehetőleg több független forrásból.
- A data/editorial.json meglévő items tömbjét kell bővíteni a jelenlegi séma szerint, egyedi id, published_at, ai_edited: true, t, s, p, src, r, c, st, time, w, cav, op mezőkkel.
- Megyei cikk esetén m mezőben a megye neve szerepeljen; sport esetén r: Sport.
- Saját megfogalmazás, elegendő ellenőrzött tény, elkülönített vélemény. Ne legyen kitalált adat, forrás vagy képcredit.
- Kép csak igazolt felhasználási joggal; egyébként üres img mező és a frontend saját illusztrációja.
- A régi azonosítókat és forráslinkeket meg kell őrizni. Publikálás előtt JSON, egyedi azonosítók és forrásduplikációk ellenőrzése.
- Közvetlen main commit friss blob SHA-val, utána visszaellenőrzés.

A szerkesztőségi munka ChatGPT-beszélgetésben történik, nem a GitHub Actions fizetős API-hívásaival. Az RSS ütemezés önmagában nem indít ChatGPT-cikkírást.
