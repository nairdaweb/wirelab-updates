# Uruchomienie updates.wirelab.pl (instrukcja dla właściciela)

Wszystko robisz raz. Zajmie około 15 minut. Wzór jest ten sam co przy status.wirelab.pl.

## 1. Repozytorium na GitHubie

1. github.com → **New repository**. Nazwa: `wirelab-updates`, konto `nairdaweb`. Widoczność: **Public**
   (darmowe Pages i minuty Actions; w repo nie ma żadnych sekretów, a prywatne pluginy mają w nim tylko
   numer wersji i datę). Bez README i licencji.
2. Wypchnij lokalne repo (robi to koordynator):
   ```sh
   git remote add origin git@github.com:nairdaweb/wirelab-updates.git
   git push -u origin main
   ```
3. **Settings → Actions → General → Workflow permissions**: zostaw **Read repository contents**.
   Workflow nie potrzebuje żadnego tokenu ani sekretu.

## 2. GitHub Pages

1. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Actions → build → Run workflow** (pierwsze uruchomienie ręcznie). Po około minucie strona działa
   pod `https://nairdaweb.github.io/wirelab-updates/`.
3. **Settings → Environments → github-pages**: wdrażać może tylko gałąź `main`. Tak zostaw.

## 3. Domena updates.wirelab.pl (nazwa.pl)

1. Panel nazwa.pl → domena `wirelab.pl` → **Strefa DNS** → dodaj rekord:

   | Pole | Wpisz |
   |---|---|
   | Nazwa | `updates.wirelab.pl` (pełna nazwa) |
   | Typ | `CNAME` |
   | Wartość | `nairdaweb.github.io` (bez kropki na końcu, bez nazwy repo) |
   | TTL | 3600 |

   Zapisz. Sprawdzenie (po kilku minutach): `dig +short updates.wirelab.pl CNAME` pokazuje
   `nairdaweb.github.io.`.
2. GitHub: **Settings → Pages → Custom domain**: `updates.wirelab.pl` → **Save**. Poczekaj, aż
   sprawdzenie DNS przejdzie (od kilku minut do godziny).
3. Zaznacz **Enforce HTTPS**, gdy stanie się dostępne (certyfikat wystawia GitHub, zwykle do 30 minut
   po sprawdzeniu DNS). Bez tego pluginy nie pobiorą danych, bo łączą się tylko po HTTPS.
4. Jeśli domena `wirelab.pl` jest już zweryfikowana w ustawieniach konta (przy status.wirelab.pl),
   nic więcej nie trzeba. Jeśli nie: avatar → **Settings → Pages → Add a domain** → `wirelab.pl`
   i rekord TXT z instrukcji GitHuba.
5. Sprawdź: `https://updates.wirelab.pl/api/index.json` zwraca JSON.

## 4. Codzienna obsługa

- **Publiczne pluginy** (topic-icons, rank-badges, shoutbox): nic nie robisz. Po `npm publish` strona
  pokaże nową wersję przy najbliższym przebiegu (co 6 h) albo od razu po **Actions → build → Run
  workflow**. Opis zmian jest brany z `CHANGELOG.md` w repo, więc najpierw wypchnij CHANGELOG.
- **Prywatne pluginy** (solved, project-card): po wdrożeniu nowej wersji:
  ```sh
  python3 scripts/bump.py nodebb-plugin-solved 1.2.0
  git commit -am "solved 1.2.0" && git push
  ```
  albo popraw `version` i `date` w `products.yml` w przeglądarce (GitHub → plik → edycja → Commit).
- **WireCap**: wersję i datę zmieniasz w `products.yml` (tak samo, `bump.py wirecap 1.3.0`). Po
  publikacji w Chrome Web Store zmień `status: soon` na `released`.
- **AmbiHog, led-auto**: są w `products.yml` jako `status: planned` (bez danych, poza stroną). Gdy
  będą gotowe, dopisz `version`, `date`, `source: manual` i zmień status.
- **Czerwony przebieg w Actions**: zwykle literówka w `products.yml` (opis w logu kroku „Build site”)
  albo chwilowa niedostępność npm lub GitHuba. Strona zostaje wtedy w poprzedniej wersji.
- **60 dni bez aktywności**: GitHub wyłącza zaplanowane przebiegi w repo bez commitów. Dostaniesz
  maila; wejdź w **Actions → build → Enable workflow**. Każdy push (np. `bump.py`) też je odnawia.

## 5. Prywatność

Pluginy pytają o `https://updates.wirelab.pl/api/<id>.json` raz na dobę zwykłym GET-em, bez parametrów
i ciasteczek. GitHub (USA) widzi adres IP serwera forum i odwiedzających stronę. W polityce prywatności
wystarczy ten sam punkt co dla status.wirelab.pl (GitHub, Data Privacy Framework). Sprawdzanie można
wyłączyć w ACP każdego pluginu („Sprawdzaj aktualizacje”).
