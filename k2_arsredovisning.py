# -*- coding: utf-8 -*-
"""
K2-årsredovisning – Fullversion för Odoo.sh / egen server.

Till skillnad från Online-XML-versionen används här riktiga Python-fält
(compute, onchange) vilket ger en betydligt smidigare användarupplevelse:
- Datum sätts automatiskt med relativedelta (ingen py.js-begränsning)
- BR/RR kan beräknas direkt vid sparande, inte bara via knapptryck
- Validering och felmeddelanden är native Python (ValidationError)
"""

import logging
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# BAS-kontomappning. Centraliserad här (i Python, inte upprepad i XML)
# så att den är enkel att underhålla och testa.
# ────────────────────────────────────────────────────────────────────────
RR_ACCOUNTS = {
    'netto':       [(3000, 3799)],
    'aktiverat':   [(3850, 3899)],
    'ovr_intakt':  [(3800, 3849), (3900, 3999)],
    'ravaror':     [(4000, 4999)],
    'externa':     [(5000, 6999)],
    'personal':    [(7000, 7699)],
    'avskriv':     [(7800, 7899)],
    'ovr_kost':    [(7900, 7999)],
    'ranteinkt':   [(8100, 8299)],
    'rantekost':   [(8400, 8499)],
    'skatt':       [(8800, 8899)],
}

BR_TILLG_ACCOUNTS = {
    'imm':         [(1000, 1099)],
    'byggnader':   [(1100, 1199)],
    'maskiner':    [(1200, 1299)],
    'fin_anl':     [(1300, 1399)],
    'varulager':   [(1400, 1499)],
    'kundford':    [(1500, 1519)],
    'ovr_ford':    [(1520, 1799)],
    'kassa':       [(1800, 1999)],
}

BR_EK_SKULD_ACCOUNTS = {
    'aktiekap':    [(2081, 2081)],
    'reservfond':  [(2083, 2083)],
    'balanserat':  [(2086, 2089)],
    'obesk':       [(2100, 2199)],
    'avsatt':      [(2200, 2299)],
    'lang':        [(2350, 2399)],
    'lev':         [(2440, 2449)],
    'skatteskd':   [(2510, 2519)],
    'ovr_kort':    [(2400, 2439), (2450, 2999)],
}


class K2Arsredovisning(models.Model):
    _name = 'k2.arsredovisning'
    _description = 'K2-årsredovisning för aktiebolag'
    _order = 'date_to desc'
    _rec_name = 'name'

    # ── Metadata ──────────────────────────────────────────────────────
    name = fields.Char(string='Referens', required=True, copy=False,
                        default=lambda self: _('Ny årsredovisning'))
    company_id = fields.Many2one('res.company', string='Företag', required=True,
                                  default=lambda self: self.env.company)
    orgnr = fields.Char(string='Organisationsnummer', related='company_id.company_registry',
                         readonly=True, store=True)
    date_from = fields.Date(string='Räkenskapsår från', required=True, copy=False)
    date_to = fields.Date(string='Räkenskapsår till', required=True, copy=False)
    date_from_prev = fields.Date(string='Föregående år från', copy=False)
    date_to_prev = fields.Date(string='Föregående år till', copy=False)
    state = fields.Selection([
        ('draft', 'Utkast'),
        ('klar', 'Klar för fastställelse'),
        ('fastställd', 'Fastställd'),
    ], string='Status', default='draft', copy=False, tracking=True)

    # ── Förvaltningsberättelse ────────────────────────────────────────
    verksamhet = fields.Text(string='Verksamhetens art och inriktning')
    handelser = fields.Text(string='Väsentliga händelser under räkenskapsåret')
    framtid = fields.Text(string='Förväntad framtida utveckling')
    miljo = fields.Text(string='Miljö- och personalinformation')
    disposition = fields.Text(string='Förslag till resultatdisposition')
    disposition_utdelning = fields.Monetary(string='Föreslagen utdelning')

    # ── Nyckeltal (beräknade, lagrade för historik) ──────────────────
    nt_netto_n = fields.Monetary(string='Nettoomsättning innevarande', compute='_compute_nyckeltal', store=True)
    nt_netto_f = fields.Monetary(string='Nettoomsättning föregående', compute='_compute_nyckeltal', store=True)
    nt_res_n = fields.Monetary(string='Resultat e. fin. innevarande', compute='_compute_nyckeltal', store=True)
    nt_res_f = fields.Monetary(string='Resultat e. fin. föregående', compute='_compute_nyckeltal', store=True)
    nt_balans_n = fields.Monetary(string='Balansomslutning innevarande', compute='_compute_nyckeltal', store=True)
    nt_balans_f = fields.Monetary(string='Balansomslutning föregående', compute='_compute_nyckeltal', store=True)
    nt_solid_n = fields.Float(string='Soliditet % innevarande', compute='_compute_nyckeltal', store=True)
    nt_solid_f = fields.Float(string='Soliditet % föregående', compute='_compute_nyckeltal', store=True)

    # ── Resultaträkning – innevarande ────────────────────────────────
    rr_netto = fields.Monetary(string='Nettoomsättning')
    rr_aktiverat = fields.Monetary(string='Aktiverat arbete för egen räkning')
    rr_ovr_intakt = fields.Monetary(string='Övriga rörelseintäkter')
    rr_ravaror = fields.Monetary(string='Råvaror / handelsvaror')
    rr_externa = fields.Monetary(string='Övriga externa kostnader')
    rr_personal = fields.Monetary(string='Personalkostnader')
    rr_avskriv = fields.Monetary(string='Av- och nedskrivningar')
    rr_ovr_kostnad = fields.Monetary(string='Övriga rörelsekostnader')
    rr_rorelseresultat = fields.Monetary(string='Rörelseresultat', compute='_compute_rr', store=True)
    rr_ranteinkt = fields.Monetary(string='Ränteintäkter')
    rr_rantekost = fields.Monetary(string='Räntekostnader')
    rr_resultat_fin = fields.Monetary(string='Resultat efter finansiella poster', compute='_compute_rr', store=True)
    rr_skatt = fields.Monetary(string='Skatt på årets resultat')
    rr_arets_resultat = fields.Monetary(string='Årets resultat', compute='_compute_rr', store=True)

    # ── Resultaträkning – föregående år ──────────────────────────────
    rr_p_netto = fields.Monetary(string='RR föreg: Nettoomsättning')
    rr_p_ravaror = fields.Monetary(string='RR föreg: Råvaror')
    rr_p_externa = fields.Monetary(string='RR föreg: Övriga externa kostnader')
    rr_p_personal = fields.Monetary(string='RR föreg: Personalkostnader')
    rr_p_avskriv = fields.Monetary(string='RR föreg: Avskrivningar')
    rr_p_rorelseresultat = fields.Monetary(string='RR föreg: Rörelseresultat', compute='_compute_rr', store=True)
    rr_p_resultat_fin = fields.Monetary(string='RR föreg: Resultat e. fin.', compute='_compute_rr', store=True)
    rr_p_skatt = fields.Monetary(string='RR föreg: Skatt')
    rr_p_arets_resultat = fields.Monetary(string='RR föreg: Årets resultat', compute='_compute_rr', store=True)

    # ── Balansräkning – Tillgångar, innevarande ──────────────────────
    bt_imm = fields.Monetary(string='Immateriella anläggningstillgångar')
    bt_byggnader = fields.Monetary(string='Byggnader och mark')
    bt_maskiner = fields.Monetary(string='Maskiner och inventarier')
    bt_fin_anl = fields.Monetary(string='Finansiella anläggningstillgångar')
    bt_anl_summa = fields.Monetary(string='Summa anläggningstillgångar', compute='_compute_br', store=True)
    bt_varulager = fields.Monetary(string='Varulager')
    bt_kundford = fields.Monetary(string='Kundfordringar')
    bt_ovr_ford = fields.Monetary(string='Övriga fordringar')
    bt_kassa = fields.Monetary(string='Kassa och bank')
    bt_oms_summa = fields.Monetary(string='Summa omsättningstillgångar', compute='_compute_br', store=True)
    bt_summa = fields.Monetary(string='SUMMA TILLGÅNGAR', compute='_compute_br', store=True)

    # ── Balansräkning – Tillgångar, föregående ───────────────────────
    bp_anl_summa = fields.Monetary(string='BR föreg: Summa anläggningstillg.')
    bp_varulager = fields.Monetary(string='BR föreg: Varulager')
    bp_kundford = fields.Monetary(string='BR föreg: Kundfordringar')
    bp_ovr_ford = fields.Monetary(string='BR föreg: Övriga fordringar')
    bp_kassa = fields.Monetary(string='BR föreg: Kassa och bank')
    bp_summa = fields.Monetary(string='BR föreg: SUMMA TILLGÅNGAR', compute='_compute_br', store=True)

    # ── Balansräkning – EK och skulder, innevarande ──────────────────
    be_aktiekap = fields.Monetary(string='Aktiekapital')
    be_reservfond = fields.Monetary(string='Reservfond')
    be_balanserat = fields.Monetary(string='Balanserat resultat')
    be_ek_summa = fields.Monetary(string='Summa eget kapital', compute='_compute_br', store=True)
    be_obesk = fields.Monetary(string='Obeskattade reserver')
    be_avsatt = fields.Monetary(string='Avsättningar')
    be_lang = fields.Monetary(string='Långfristiga skulder')
    be_lev = fields.Monetary(string='Leverantörsskulder')
    be_skatteskuld = fields.Monetary(string='Skatteskulder')
    be_ovr_kort = fields.Monetary(string='Övriga kortfristiga skulder')
    be_kort_summa = fields.Monetary(string='Summa kortfristiga skulder', compute='_compute_br', store=True)
    be_summa = fields.Monetary(string='SUMMA EK OCH SKULDER', compute='_compute_br', store=True)

    # ── Balansräkning – EK och skulder, föregående ───────────────────
    bp_aktiekap = fields.Monetary(string='BR föreg: Aktiekapital')
    bp_balanserat = fields.Monetary(string='BR föreg: Balanserat resultat')
    bp_ek_summa = fields.Monetary(string='BR föreg: Summa eget kapital', compute='_compute_br', store=True)
    bp_lang = fields.Monetary(string='BR föreg: Långfristiga skulder')
    bp_lev = fields.Monetary(string='BR föreg: Leverantörsskulder')
    bp_ovr_kort = fields.Monetary(string='BR föreg: Övriga kortfristiga skulder')
    bp_ek_skuld_summa = fields.Monetary(string='BR föreg: SUMMA EK OCH SKULDER', compute='_compute_br', store=True)

    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # ── Noter ─────────────────────────────────────────────────────────
    not_principer = fields.Text(string='Not 1 – Redovisningsprinciper')
    not_revisor = fields.Text(string='Not 2 – Arvode till revisorer')
    not_personal = fields.Text(string='Not 3 – Anställda och löner')
    not_avskrivningar = fields.Text(string='Not 4 – Avskrivningar')
    not_anlaggningstillgangar = fields.Text(string='Not 5 – Anläggningstillgångar')
    not_aktiekapital = fields.Text(string='Not 6 – Aktiekapital')
    not_obeskattade = fields.Text(string='Not 7 – Obeskattade reserver')
    not_dotterbolag = fields.Text(string='Not 8 – Andelar i koncernföretag (dotterbolag)')
    not_sakerheter = fields.Text(string='Not – Säkerheter och eventualförpliktelser')
    not_handelser_ef = fields.Text(string='Not – Händelser efter balansdagen')
    not_nyckeltal = fields.Text(string='Not – Nyckeltalsdefinitioner',
                                 default=lambda self: _(
                                     "Soliditet: Eget kapital och obeskattade reserver "
                                     "(med avdrag för uppskjuten skatt) i förhållande "
                                     "till balansomslutningen."
                                 ))

    # ── Underskrifter ─────────────────────────────────────────────────
    sign_ort = fields.Char(string='Ort', default='Stockholm')
    sign_datum = fields.Date(string='Datum för underskrift')
    sign_styrelse_ids = fields.One2many('k2.styrelseledamot', 'arsredovisning_id', string='Styrelseledamöter')
    sign_vd = fields.Char(string='Verkställande direktör')
    sign_revisor = fields.Char(string='Revisorns namn')
    sign_byra = fields.Char(string='Revisionsbyrå')

    # ── Fastställelseintyg ────────────────────────────────────────────
    fast_ort = fields.Char(string='Ort (fastställelseintyg)', default='Stockholm')
    fast_datum = fields.Date(string='Datum för undertecknande av intyget')
    fast_stamma_datum = fields.Date(string='Datum då årsstämman hölls')
    fast_styrelseledamot_id = fields.Many2one('k2.styrelseledamot', string='Undertecknande styrelseledamot',
                                               domain="[('arsredovisning_id', '=', id)]")

    # ───────────────────────────────────────────────────────────────────
    # Onchange: sätt smarta defaults när företag ändras / vid skapande
    # ───────────────────────────────────────────────────────────────────

    @api.model
    def default_get(self, fields_list):
        """Smart standardperiod: föregående kalenderår."""
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        last_year = today.year - 1
        res.setdefault('date_from', fields.Date.to_date('%d-01-01' % last_year))
        res.setdefault('date_to', fields.Date.to_date('%d-12-31' % last_year))
        return res

    @api.onchange('date_from', 'date_to')
    def _onchange_period(self):
        """Beräkna jämförelseår automatiskt med relativedelta (ingen py.js-begränsning här)."""
        for rec in self:
            if rec.date_from and rec.date_to:
                rec.date_from_prev = rec.date_from - relativedelta(years=1)
                rec.date_to_prev = rec.date_to - relativedelta(years=1)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('Startdatum kan inte vara efter slutdatum.'))

    # ───────────────────────────────────────────────────────────────────
    # Beräknade summeringsfält
    # ───────────────────────────────────────────────────────────────────

    @api.depends('rr_netto', 'rr_aktiverat', 'rr_ovr_intakt', 'rr_ravaror', 'rr_externa',
                 'rr_personal', 'rr_avskriv', 'rr_ovr_kostnad', 'rr_ranteinkt', 'rr_rantekost',
                 'rr_skatt', 'rr_p_netto', 'rr_p_ravaror', 'rr_p_externa', 'rr_p_personal',
                 'rr_p_avskriv', 'rr_p_skatt')
    def _compute_rr(self):
        for rec in self:
            intakter = rec.rr_netto + rec.rr_aktiverat + rec.rr_ovr_intakt
            kostnader = rec.rr_ravaror + rec.rr_externa + rec.rr_personal + rec.rr_avskriv + rec.rr_ovr_kostnad
            rec.rr_rorelseresultat = intakter - kostnader
            rec.rr_resultat_fin = rec.rr_rorelseresultat + rec.rr_ranteinkt - rec.rr_rantekost
            rec.rr_arets_resultat = rec.rr_resultat_fin - rec.rr_skatt

            p_kostnader = rec.rr_p_ravaror + rec.rr_p_externa + rec.rr_p_personal + rec.rr_p_avskriv
            rec.rr_p_rorelseresultat = rec.rr_p_netto - p_kostnader
            rec.rr_p_resultat_fin = rec.rr_p_rorelseresultat
            rec.rr_p_arets_resultat = rec.rr_p_resultat_fin - rec.rr_p_skatt

    @api.depends('bt_imm', 'bt_byggnader', 'bt_maskiner', 'bt_fin_anl', 'bt_varulager',
                 'bt_kundford', 'bt_ovr_ford', 'bt_kassa', 'be_aktiekap', 'be_reservfond',
                 'be_balanserat', 'rr_arets_resultat', 'be_obesk', 'be_avsatt', 'be_lang',
                 'be_lev', 'be_skatteskuld', 'be_ovr_kort', 'bp_anl_summa', 'bp_varulager',
                 'bp_kundford', 'bp_ovr_ford', 'bp_kassa', 'bp_aktiekap', 'bp_balanserat',
                 'rr_p_arets_resultat', 'bp_lang', 'bp_lev', 'bp_ovr_kort')
    def _compute_br(self):
        for rec in self:
            rec.bt_anl_summa = rec.bt_imm + rec.bt_byggnader + rec.bt_maskiner + rec.bt_fin_anl
            rec.bt_oms_summa = rec.bt_varulager + rec.bt_kundford + rec.bt_ovr_ford + rec.bt_kassa
            rec.bt_summa = rec.bt_anl_summa + rec.bt_oms_summa

            rec.be_ek_summa = rec.be_aktiekap + rec.be_reservfond + rec.be_balanserat + rec.rr_arets_resultat
            rec.be_kort_summa = rec.be_lev + rec.be_skatteskuld + rec.be_ovr_kort
            rec.be_summa = (rec.be_ek_summa + rec.be_obesk + rec.be_avsatt
                             + rec.be_lang + rec.be_kort_summa)

            rec.bp_summa = rec.bp_anl_summa + rec.bp_varulager + rec.bp_kundford + rec.bp_ovr_ford + rec.bp_kassa
            rec.bp_ek_summa = rec.bp_aktiekap + rec.bp_balanserat + rec.rr_p_arets_resultat
            rec.bp_ek_skuld_summa = rec.bp_ek_summa + rec.bp_lang + rec.bp_lev + rec.bp_ovr_kort

    @api.depends('rr_netto', 'rr_p_netto', 'rr_resultat_fin', 'rr_p_resultat_fin',
                 'bt_summa', 'bp_summa', 'be_ek_summa', 'bp_ek_summa')
    def _compute_nyckeltal(self):
        for rec in self:
            rec.nt_netto_n = rec.rr_netto
            rec.nt_netto_f = rec.rr_p_netto
            rec.nt_res_n = rec.rr_resultat_fin
            rec.nt_res_f = rec.rr_p_resultat_fin
            rec.nt_balans_n = rec.bt_summa
            rec.nt_balans_f = rec.bp_summa
            rec.nt_solid_n = round(rec.be_ek_summa / rec.bt_summa * 100, 1) if rec.bt_summa else 0.0
            rec.nt_solid_f = round(rec.bp_ek_summa / rec.bp_summa * 100, 1) if rec.bp_summa else 0.0

    # ───────────────────────────────────────────────────────────────────
    # Datahämtning från bokföringen
    # ───────────────────────────────────────────────────────────────────

    def _get_balance(self, date_from, date_to, account_ranges, sign=1):
        """Summerar debet-kredit för konton inom BAS-intervall under perioden."""
        self.ensure_one()
        if not self.company_id:
            return 0.0

        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
        ]
        or_domain = []
        for i, (low, high) in enumerate(account_ranges):
            if i > 0:
                or_domain.append('|')
            or_domain += [
                ('account_id.code', '>=', str(low).zfill(4)),
                ('account_id.code', '<=', str(high).zfill(4) + 'ZZZZ'),
            ]
        domain += or_domain

        result = self.env['account.move.line'].read_group(domain, ['debit:sum', 'credit:sum'], [])
        if result:
            debit = result[0].get('debit') or 0.0
            credit = result[0].get('credit') or 0.0
            return round((debit - credit) * sign, 0)
        return 0.0

    def _get_balance_to_date(self, date_to, account_ranges, sign=1):
        return self._get_balance('1900-01-01', date_to, account_ranges, sign)

    def action_fetch_from_accounting(self):
        """Hämtar RR/BR/personaldata från bokföringen och HR-modulen."""
        self.ensure_one()
        if not self.company_id or not self.date_from or not self.date_to:
            raise UserError(_('Välj företag och räkenskapsår innan du hämtar data.'))

        if not self.date_from_prev or not self.date_to_prev:
            self._onchange_period()

        df, dt = self.date_from, self.date_to
        dfp, dtp = self.date_from_prev, self.date_to_prev

        def rr(key, prev=False):
            ranges = RR_ACCOUNTS[key]
            sign = -1 if key in ('ravaror', 'externa', 'personal', 'avskriv', 'ovr_kost', 'rantekost', 'skatt') else 1
            d_from, d_to = (dfp, dtp) if prev else (df, dt)
            return self._get_balance(d_from, d_to, ranges, sign)

        def bt(key, prev=False):
            ranges = BR_TILLG_ACCOUNTS[key]
            d_to = dtp if prev else dt
            return self._get_balance_to_date(d_to, ranges, 1)

        def be(key, prev=False):
            ranges = BR_EK_SKULD_ACCOUNTS[key]
            d_to = dtp if prev else dt
            return self._get_balance_to_date(d_to, ranges, -1)

        vals = {
            'rr_netto': rr('netto'), 'rr_aktiverat': rr('aktiverat'), 'rr_ovr_intakt': rr('ovr_intakt'),
            'rr_ravaror': rr('ravaror'), 'rr_externa': rr('externa'), 'rr_personal': rr('personal'),
            'rr_avskriv': rr('avskriv'), 'rr_ovr_kostnad': rr('ovr_kost'),
            'rr_ranteinkt': rr('ranteinkt'), 'rr_rantekost': rr('rantekost'), 'rr_skatt': rr('skatt'),

            'rr_p_netto': rr('netto', True), 'rr_p_ravaror': rr('ravaror', True),
            'rr_p_externa': rr('externa', True), 'rr_p_personal': rr('personal', True),
            'rr_p_avskriv': rr('avskriv', True), 'rr_p_skatt': rr('skatt', True),

            'bt_imm': bt('imm'), 'bt_byggnader': bt('byggnader'), 'bt_maskiner': bt('maskiner'),
            'bt_fin_anl': bt('fin_anl'), 'bt_varulager': bt('varulager'), 'bt_kundford': bt('kundford'),
            'bt_ovr_ford': bt('ovr_ford'), 'bt_kassa': bt('kassa'),

            'bp_anl_summa': bt('imm', True) + bt('byggnader', True) + bt('maskiner', True) + bt('fin_anl', True),
            'bp_varulager': bt('varulager', True), 'bp_kundford': bt('kundford', True),
            'bp_ovr_ford': bt('ovr_ford', True), 'bp_kassa': bt('kassa', True),

            'be_aktiekap': be('aktiekap'), 'be_reservfond': be('reservfond'), 'be_balanserat': be('balanserat'),
            'be_obesk': be('obesk'), 'be_avsatt': be('avsatt'), 'be_lang': be('lang'),
            'be_lev': be('lev'), 'be_skatteskuld': be('skatteskd'), 'be_ovr_kort': be('ovr_kort'),

            'bp_aktiekap': be('aktiekap', True), 'bp_balanserat': be('balanserat', True),
            'bp_lang': be('lang', True), 'bp_lev': be('lev', True), 'bp_ovr_kort': be('ovr_kort', True),
        }
        self.write(vals)

        # Not 3 – medelantal anställda (om HR-appen finns)
        if 'hr.employee' in self.env and not (self.not_personal or '').strip():
            Employee = self.env['hr.employee']
            antal = Employee.search_count([('company_id', '=', self.company_id.id), ('active', '=', True)])
            try:
                kvinnor = Employee.search_count([
                    ('company_id', '=', self.company_id.id), ('active', '=', True), ('gender', '=', 'female')
                ])
            except Exception:
                kvinnor = 0

            text = _("Medelantalet anställda under året var %d, varav %d kvinnor.") % (antal, kvinnor) if kvinnor \
                else _("Medelantalet anställda under året var %d.") % antal
            text += _(
                "\n⚠️ OBS: siffran är antal aktiva anställda i registret just nu, inte ett "
                "historiskt beräknat medelantal. Kontrollera och justera vid behov."
            )
            self.not_personal = text

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Klart!'),
                'message': _('Resultat- och balansräkning har hämtats från bokföringen.'),
                'type': 'success',
            }
        }

    def action_duplicate_to_next_year(self):
        """Wizard-anrop: duplicera till nästa år, rensa siffror, behåll text."""
        self.ensure_one()
        new = self.copy(default={
            'name': _('Årsredovisning %s') % (self.date_to.year + 1),
            'date_from': self.date_from + relativedelta(years=1),
            'date_to': self.date_to + relativedelta(years=1),
            'state': 'draft',
            # Nollställ siffror – behåll löpande text via copy default
            'rr_netto': 0, 'rr_aktiverat': 0, 'rr_ovr_intakt': 0, 'rr_ravaror': 0,
            'rr_externa': 0, 'rr_personal': 0, 'rr_avskriv': 0, 'rr_ovr_kostnad': 0,
            'rr_ranteinkt': 0, 'rr_rantekost': 0, 'rr_skatt': 0,
        })
        new._onchange_period()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'k2.arsredovisning',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }


class K2Styrelseledamot(models.Model):
    _name = 'k2.styrelseledamot'
    _description = 'Styrelseledamot för K2-årsredovisning'
    _order = 'sequence, id'

    arsredovisning_id = fields.Many2one('k2.arsredovisning', string='Årsredovisning',
                                         required=True, ondelete='cascade')
    sequence = fields.Integer(string='Ordning', default=10)
    name = fields.Char(string='Namn', required=True)
    befattning = fields.Selection([
        ('ordforande', 'Styrelseordförande'),
        ('ledamot', 'Styrelseledamot'),
        ('suppleant', 'Styrelsesuppleant'),
        ('vd', 'Verkställande direktör'),
    ], string='Befattning', required=True, default='ledamot')
