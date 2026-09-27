# Overenie verzie 0.3.0

Overované 27. septembra 2026 na macOS 26.6.2 / Apple Silicon, Python 3.11.15, Qt 6.11.2, OpenCV 5.0.0.

## Obrazové jadro

**92 automatických testov prešlo.** Pokrývajú:

- zarovnanie textúrovaného disku pri rozdielnych EV, posune, mierke a otočení,
- ľubovoľný počet expozícií a výber referencie,
- nízku istotu pri disku bez detailov a oddelenie prepáleného disku od širšieho hala,
- obnovu rôznych jasov prepálených v normálnej expozícii a ochranu použiteľných detailov pred prepáleným vstupom pri fúzii,
- platné okraje/masky a pôvodné lineárne hodnoty v HDR,
- FITS integer/float, BSCALE/BZERO, BLANK/NaN, RGB/mono, gzip a komprimovanú HDU,
- expozičné časy, jednotky counts/rate, nekompatibilné jednotky a saturáciu FITS,
- prijatie RGB FITS so zvyšným Bayer údajom a odmietnutie nevyvolaných 2D CFA či spektrálnych/časových kociek,
- neutrálnu farbu, zachovanie jasu a nemennosť originálu pri vyvážení farieb,
- presnosť 16-bit TIFF, komprimované TIFF vstupy a HDR hodnoty nad 1,
- chybné vstupy a konečné hodnoty výstupu.

## Rozhranie

Verzia 0.3 pridala 21 regresných testov rozhrania/exportu a 11 testov dokončovacích úprav. Overený je štart z pracovného priečinka `/`, absolútny predvolený priečinok Obrázky, prázdny filter súborového dialógu, PNG/TIFF/HDR export, chyba oprávnenia a opakovaný úspešný export. Orez myšou, podpis a režimy hviezd sa premietajú do rastrového exportu; lineárny HDR zostáva bez týchto úprav. Testy kontrolujú aj zhodné rozmery náhľadu a porovnania po oreze a obnovenie nastavení cez Reset.


Integračne overené: import piatich FITS → pridanie na sedem → zmena referencie a odobratie na šesť → načítanie EV z EXPTIME → zachovanie ručne upravených EV → HDR → ručné doladenie šiestej snímky → 16-bit TIFF export. Neplatný súbor nezničí predchádzajúcu reláciu; odobratie všetkých snímok správne zakáže skladanie a export.

Pôvodné overenie zahŕňalo aj syntetické demo, Natural/Mineral Moon, porovnanie pred/po, PNG a lineárny HDR export. Úprava EV zneplatní starý export, výmena snímok zneplatní registráciu. Prvý import skutočných dát nahrádza syntetické demo.

Samostatný Mac balík s FITS podporou úspešne načítal päť syntetických FITS vrátane komprimovanej obrazovej HDU a vytvoril ich HDR cez grafické rozhranie. Finálny balík po opravách DWARF importu bol znovu zostavený, spustený a cez grafické rozhranie načítal všetky štyri skutočné používateľove FITS; viditeľná je voľba referencie, expozičnej fúzie, upozornenie na časy a nový posuvník farieb. Výpočet finálnej fúzie a exportov bol overený rovnakým obrazovým jadrom zo zdrojového kódu.

## Súkromná praktická skúška

Čítanie bolo lokálne overené aj na štyroch RGB FITS z DWARF s uloženým senzorovým údajom BAYERPAT. Dva detailné zábery sa registrovali podľa povrchu s mediánom odchýlky zhodných bodov pod štvrť pixela. Pri prepálenom zábere registrácia použila okraj disku, nízku istotu a upozornenie na ručnú kontrolu.

Používateľove snímky, názvy súborov, výsledky a referenčná fotografia nie sú súčasťou verejného repozitára ani nových distribučných balíkov. Verejné demo a testovacie scény sú procedurálne generované.

## Prenositeľnosť

Závislosti sa podarilo vyriešiť pre Windows x64 a Linux x64 / glibc 2.34+. Tieto operačné systémy tu neboli spustené. Ich spúšťače a natívne zostavenia sú pripravené, ale ich beh musí overiť cieľový systém. Aktuálny stav zostavení je dostupný v záložke Actions repozitára.

Podpis finálneho ZIP balíka bol úspešne overený aj po rozbalení do čistého dočasného priečinka. Aplikácia je ad-hoc podpísaná; nejde o Apple Developer notarizáciu.
