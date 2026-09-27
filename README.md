# Lunar HDR Studio

Lokálna desktopová aplikácia pre skladanie dvoch alebo viacerých expozícií Mesiaca a tvorbu vzhľadu **Mineral Moon**. Verzia **0.3.0** podporuje FITS, ľubovoľný počet expozícií, hviezdne pozadie, vlastný podpis a orez obrázka. Fotografie sa nikam neposielajú. Rozhranie je v slovenčine.

![Lunar HDR Studio so syntetickou ukážkou](docs/screenshot.png)

## Rýchly štart

**Hotové aplikácie:** stiahni ZIP pre svoj systém zo sekcie [Releases](https://github.com/Kwispy232/lunar-hdr-studio/releases). Na Macu otvor `LunarHDR.app`; Python nie je potrebný. Dostupné platformy závisia od úspešne dokončených zostavení.

**Zo zdrojového kódu na macOS, Windows a Linuxe:** nainštaluj [Python 3.11 alebo novší](https://www.python.org/downloads/). Potom spusti:

- Windows: dvojklik na `run.bat`.
- macOS: dvojklik na `run.command`.
- Linux: `sh run.sh`.

Spúšťače vytvoria lokálne prostredie `.venv` a nainštalujú závislosti. Na prvé spustenie treba internet. Na Linuxe treba grafické prostredie a systémové knižnice Qt/X11 alebo Wayland; napríklad Ubuntu môže potrebovať `libxcb-cursor0` a `libxkbcommon-x11-0`.

Pripnuté binárne závislosti cielia na moderné systémy: macOS 13+, Windows 10/11 a Linux x86_64 s glibc 2.34+ (napríklad Ubuntu 22.04+). Dostupnosť balíkov bola overená pre macOS ARM, Windows x64 a Linux x64; samotná aplikácia bola spustená iba na tomto Macu.

Alternatíva v termináli:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

## Pracovný postup

1. Načítaj dve alebo viac fotografií. Ďalšie môžeš pridávať do zoznamu, jednotlivé snímky nahradiť alebo odstrániť. Ako referenciu vyber ostrý, dobre exponovaný záber; určuje výsledný výrez a rozmery.
2. Nastav rozdiely EV voči referenčnému záberu. Pri dostupnom expozičnom čase v každom FITS sa predvyplnia z hlavičiek. Napríklad časy 1/1000, 1/250 a 1/60 s pri rovnakom ISO a clone približne zodpovedajú −2, 0 a +2 EV. Pri chýbajúcich údajoch nastav EV ručne; predvolené nuly nie sú odhadom skutočnej expozície. Z JPEG EXIF sa časy automaticky nezisťujú.
3. Vyber HDR alebo expozičnú fúziu a spusti zarovnanie a skladanie. Skontroluj diagnostiku zarovnania; pri neistej registrácii použi ručné doladenie.
4. Vyskúšaj **Mineral Moon**, prípadne uprav saturáciu, teplotu, kontrast, detaily a ďalšie posuvníky. Porovnaj výsledok s normálnou expozíciou.
5. V časti **Dokončenie** dole v pravom paneli uprav pozadie: ponechaj pôvodné hviezdy, potlač malé svetlé body alebo pridaj syntetické hviezdy ako vizuálny efekt. Tieto voľby nemenia pôvodné súbory.
6. Vyber orez myšou a podľa potreby zapni vlastný textový podpis. Orez môžeš zrušiť a podpis upraviť.
7. Exportuj hotový obrázok ako PNG/JPEG alebo 16-bit TIFF. Pre ďalšie HDR spracovanie exportuj lineárny súbor Radiance `.hdr`.

## Čo jednotlivé režimy robia

**HDR z bežných obrázkov** linearizuje vstupné sRGB farby, zohľadní zadané EV a vážene spojí expozície. Výstup v plávajúcej desatinnej čiarke zachováva hodnoty nad 1. Náhľad používa mapovanie tónov. Ide o relatívne HDR pri predpoklade sRGB odozvy, nie o kalibráciu senzora alebo presné meranie jasu.

**HDR z FITS** používa pôvodné lineárne vzorky po aplikovaní FITS mierky `BSCALE/BZERO`. Kontrast náhľadu nemení dáta použité na skladanie. Časy `EXPTIME` umožnia prepočet intenzity na jednotku času; vstupy už označené ako intenzita za sekundu sa nedelia časom znova. Zábery musia mať zlučiteľné jednotky a kalibráciu. Podporované sú ADU, DN, counts a elektróny/fotóny aj ich hodnoty za sekundu; iné kalibrované jednotky, napríklad Jy/sr, treba najprv previesť alebo použiť vizuálnu fúziu. Automatický odhad EV predpokladá rovnaký gain, clonu a filtre. Pri pomere časov nad 1000× aplikácia zobrazí upozornenie na kontrolu normalizácie. Pri už jasovo normalizovaných stackoch skontroluj ručne EV; celkový integračný čas nemusí vyjadrovať rozdiel jasu uložených pixelov. Bežné sRGB obrázky a FITS s fyzikálnymi jednotkami nespájaj do jedného rádiometrického HDR; na vizuálne spojenie použi expozičnú fúziu.

**Expozičná fúzia** spája použiteľné oblasti expozícií do zobraziteľného obrázka. Tento režim nie je lineárny HDR a nemá export HDR radiancie. Rozdiel medzi HDR a expozičnou fúziou vysvetľuje aj [dokumentácia OpenCV](https://docs.opencv.org/4.12.0/d2/df0/tutorial_py_hdr.html).

**Mineral Moon** zvýrazňuje existujúce farebné rozdiely. Posuvník **Neutralizácia farieb** najprv vyváži priemerný farebný nádych jasnej časti disku; predpokladá približne neutrálny Mesiac a dá sa znížiť alebo vypnúť. Preset Mineral Moon ho zapína, aby nezosilňoval iba celkový žltý či zelený nádych vstupu. Nevytvára skutočné farebné informácie z monochromatickej snímky a nie je mineralogickou analýzou. Kvalitu ovplyvní farebný šum a vyváženie bielej.

PNG/JPEG/TIFF obsahujú úpravy z posuvníkov, zvolené hviezdne pozadie, orez a podpis. Radiance HDR obsahuje celé základné lineárne zlúčenie, bez kreatívnych úprav, orezu, podpisu a mapovania tónov. Pridané hviezdy sú deterministický vizuálny efekt, nie zaznamenané astronomické objekty. Potlačenie hviezd je odhad malých svetlých bodov mimo disku, preto skontroluj náhľad.

Exportný dialóg začína v absolútnej ceste priečinka Obrázky (prípadne v domovskom priečinku). Po úspešnom exporte si počas otvorenej relácie pamätá zvolený priečinok. Chyba zápisu zobrazí konkrétny cieľ a vysvetlenie; výsledok ostáva pripravený na opakovaný export.

## Vstupy a praktické hranice

- JPEG, PNG a TIFF; 8-bit a 16-bit vstupy, RGB aj odtiene sivej.
- FITS (`.fits`, `.fit`, `.fts`, aj gzip a `.fits.fz`): 2D monochromatické snímky a RGB obrazové polia. Použije sa prvá obrazová HDU, vrátane obrazového rozšírenia a komprimovanej HDU. Podporované sú celočíselné aj plávajúce hodnoty a FITS škálovanie; pracovné obrazové polia používajú float32.
- Úroveň saturácie FITS sa číta zo `SATURATE`/`SATLEVEL`/`SATURLEV`, inak sa pri celočíselných dátach použije strop úložného typu. Ak senzor saturuje skôr, správnu úroveň doplň do FITS hlavičky. Maximum plávajúcej snímky sa automaticky nepovažuje za prepálenie.
- Neplatné FITS vzorky (NaN/Inf/BLANK) sa maskujú. Záporné kalibrované vzorky sa neodsúvajú individuálnym pripočítaním konštanty; pri nezápornom HDR výstupe sa záporný výsledok oreže s upozornením. Spektrálne/časové kocky a 2D nevyvolané Bayer dáta sa nepovažujú za RGB; najprv ich vyvolaj alebo vyber obrazovú rovinu. Trojkanálové RGB exporty so zvyšným údajom BAYERPAT (napríklad DWARF) sa načítajú ako hotové RGB s upozornením, bez opakovaného debayerovania.
- Pre fotoaparátový RAW alebo SER najprv exportuj farebný TIFF. Pri exporte použi sRGB; plná správa ICC profilov a RAW vyvolávanie nie sú súčasťou tejto verzie.
- Zábery by mali zachytávať tú istú fázu Mesiaca krátko po sebe, s viditeľným diskom a spoločnými detailmi. Extrémny orez, mraky, slabý signál alebo úplné prepálenie môžu znemožniť automatické zarovnanie.
- Registrácia podporuje posun, mierku a otočenie. Nekompenzuje atmosférické chvenie jednotlivých oblastí ani stopy pohybujúcich sa hviezd.
- Detail prepálený vo všetkých záberoch nemožno obnoviť. Počet snímok nemá pevný limit v rozhraní; veľa záberov v plnom rozlíšení potrebuje adekvátnu RAM.
- Táto verzia nemá ukladanie a obnovu celých rozpracovaných projektov.

## Ukážka

Dodané demo je pôvodný procedurálne vygenerovaný obraz s označením **SYNTHETIC DEMO**. Neobsahuje používateľove fotografie ani externú referenciu. Slúži na skúšanie registrácie a ovládania; nie je skutočnou fotografiou Mesiaca, mapou jeho povrchu ani mineralogickými dátami. Generátor je v `lunarhdr/publicdemo.py`, pôvod obrázkov opisuje `lunarhdr/assets/PROVENANCE.md`.

## Samostatné aplikácie

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
python build.py
```

Výsledok je v `dist/`. Samostatný balík sa zostavuje na cieľovom operačnom systéme a architektúre. Workflow `.github/workflows/build.yml` testuje a pripravuje macOS ARM, macOS Intel, Windows a Linux buildy pri pushi do `main`, pull requeste alebo manuálnom spustení. Výsledné ZIP archívy nájdeš medzi artefaktmi konkrétneho behu v GitHub Actions. Runner platformy vychádzajú z [dokumentácie GitHub](https://docs.github.com/en/actions/reference/runners/github-hosted-runners). [Qt for Python](https://doc.qt.io/qtforpython-6.8/deployment/index.html) podporuje tieto tri desktopové platformy.

Mac balík je lokálny vývojový build bez Apple Developer notarizácie. Lokálne a CI overenia opisuje `VALIDATION.md`; dokončenie buildu nenahrádza vizuálne odskúšanie na cieľovom počítači.

## Technológie

Python, PySide6/Qt, OpenCV, NumPy, Pillow, tifffile a Astropy. Verzie sú pripnuté v `requirements.txt`. FITS škálovanie a HDU čítanie používa [Astropy FITS](https://docs.astropy.org/en/stable/io/fits/usage/image.html). Qt/PySide sa používajú dynamicky; informácie o licenciách závislostí sú v ich distribúciách. Pribalené licenčné oznámenia sú v `lunarhdr/assets/licenses/`. Verejné buildy používajú tieto dynamické knižnice; Apple Developer notarizácia a podpis Windows nie sú nastavené.
