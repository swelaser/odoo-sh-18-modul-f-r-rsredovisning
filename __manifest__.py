# -*- coding: utf-8 -*-
{
    'name': 'Årsredovisning K2 – Aktiebolag (Odoo.sh / Self-hosted)',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Komplett K2-årsredovisning för aktiebolag med automatisk datahämtning från bokföringen',
    'description': """
        Årsredovisning K2 – Fullversion för Odoo.sh / egen server
        ============================================================
        Till skillnad från Online-versionen (XML-only) har denna fullversion:

        - Riktiga Python-modeller med beräknade fält (onchange, compute)
        - Automatisk hämtning av RR/BR direkt från bokföringen utan knapptryck
          (beräknas live när företag/datum ändras)
        - Smart standardperiod: föregående kalenderår, med korrekt
          jämförelseår beräknat
        - Automatisk hämtning av medelantal anställda från HR-modulen
        - PDF + riktig DOCX-export via python-docx (kräver ingen extern
          tjänst, fungerar direkt i Word/LibreOffice utan mellansteg)
        - Grund förberedd för iXBRL-export (kräver separat avtal med
          Bolagsverket för faktisk inlämning - se README)
        - Wizard för att duplicera till nästa år med korrekt fältrensning

        Förutsätter Odoo.sh, Docker-baserad installation, eller annan
        miljö där anpassade Python-moduler kan installeras.
    """,
    'author': 'Custom',
    'depends': ['account', 'l10n_se', 'base_setup'],
    'external_dependencies': {
        'python': ['python-docx'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/k2_arsredovisning_views.xml',
        'views/k2_menu_views.xml',
        'wizard/k2_duplicate_wizard_views.xml',
        'report/k2_report_actions.xml',
        'report/k2_report_templates.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
