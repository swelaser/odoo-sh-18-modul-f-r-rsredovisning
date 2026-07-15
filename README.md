# Årsredovisning K2 – Fullversion för Odoo.sh / egen server

## Skillnad mot Online-versionen

Den här modulen är en **riktig Python-modul** och kräver Odoo.sh, en
Docker-baserad installation, eller annan miljö där anpassade Python-moduler
tillåts (alltså **inte** Odoo Online/SaaS, som bara stödjer XML-only-moduler).

### Vad som blir bättre jämfört med Online-versionen

| Funktion | Online (XML-only) | Denna fullversion |
|---|---|---|
| Standardperiod | Fast text, klientbegränsad | `default_get` + `relativedelta`, helt korrekt |
| Jämförelseår | Manuellt fält | `onchange` beräknar automatiskt |
| BR/RR-summor | Manuellt ifyllda fält | Riktiga `compute`-fält, alltid korrekta |
| Hämta från bokföring | Server action (fungerar, men begränsad) | Vanlig knapp-metod, enklare att underhålla |
| Word-export | HTML-nedladdning → öppna i Word manuellt | **Riktig .docx** direkt via `python-docx`, en knapptryckning |
| Styrelseledamöter | Fritext (en rad per ledamot) | Egen modell (`k2.styrelseledamot`), kan återanvändas i fastställelseintyget |
| Duplicera till nästa år | Kopierar allt (inkl. siffror) | Wizard som nollställer siffror men behåller text |
| Validering | Ingen | `@api.constrains` ger tydliga felmeddelanden |

---

## Installation

### Krav
- Odoo 19.0 på Odoo.sh, Docker, eller annan self-hosted miljö
- Python-paketet `python-docx` (för Word-export)
- Moduler: `account`, `l10n_se`

### Steg

**Odoo.sh:**
1. Lägg modulmappen `arsredovisning_k2_sh` i er repos `custom_addons`-mapp (eller motsvarande sökväg konfigurerad i `.odoo.sh`-inställningarna)
2. Lägg till `python-docx` i `requirements.txt` i reporoten
3. Pusha till er Odoo.sh-branch – byggprocessen installerar paketet automatiskt
4. Gå till Appar → uppdatera applistan → installera "Årsredovisning K2"

**Docker / egen server:**
```bash
# Kopiera modulen till addons-mappen
cp -r arsredovisning_k2_sh /path/to/odoo/addons/

# Installera Python-beroendet
pip install python-docx --break-system-packages

# Starta om och uppdatera modullistan
docker exec -it <container> odoo -u arsredovisning_k2_sh -d <databas> --stop-after-init
```

---

## ⚠️ Viktigt: Digital inlämning till Bolagsverket – vad som INTE ingår

Den här modulen genererar **PDF och Word**, inte ett format som Bolagsverket
accepterar för digital inlämning. Innan ni planerar er process, läs detta noga:

1. **Bolagsverket kräver iXBRL, inte PDF eller HTML.** iXBRL är en webbsida
   med inbäddade maskinläsbara XBRL-taggar mot en officiell taxonomi – ett
   helt annat tekniskt format än det vi genererar här.

2. **Man kan inte bygga och ladda upp en egen iXBRL-fil.** Bolagsverket kräver
   att leverantören har tecknat avtal och genomgått teknisk kvalitetssäkring.
   En egenbyggd Odoo-modul – hur korrekt den än är tekniskt – skulle bli
   avvisad eftersom den inte kommer från en godkänd leverantör.

3. **Underskriften sker med BankID i Bolagsverkets egen tjänst**, inte i Odoo.

### Rekommenderad väg framåt om ni vill ha digital inlämning

- **Enklast:** Exportera bokföringen som SIE4-fil (stöds redan i Odoo) och
  ladda upp den i en tjänst med befintligt Bolagsverket-avtal, t.ex.
  DigitalK2 eller Wolters Kluwers Bokslut. De genererar korrekt iXBRL och
  hanterar BankID-signeringen.
- **Större investering:** Om ni vill bygga en egen lösning krävs ett separat
  avtal med Bolagsverket (teknisk kvalitetssäkring), och en betydligt större
  utvecklingsinsats för att generera giltig iXBRL enligt taxonomin – det är
  ett fristående projekt, inte en utbyggnad av den här modulen.

Den här modulen är ett utmärkt internt verktyg för att sammanställa
årsredovisningen och ha kontroll över siffrorna, men slutsteget till
Bolagsverket görs idag bäst via en redan godkänd extern tjänst.

---

## Filstruktur

```
arsredovisning_k2_sh/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── k2_arsredovisning.py    # Huvudmodell + styrelseledamot-modell
│   └── k2_docx_export.py       # Word-export via python-docx
├── wizard/
│   ├── __init__.py
│   ├── k2_duplicate_wizard.py
│   └── k2_duplicate_wizard_views.xml
├── views/
│   ├── k2_arsredovisning_views.xml
│   └── k2_menu_views.xml
├── report/
│   ├── k2_report_actions.xml
│   └── k2_report_templates.xml
├── security/
│   └── ir.model.access.csv
└── data/
    └── sequence_data.xml
```

## Licens

LGPL-3
