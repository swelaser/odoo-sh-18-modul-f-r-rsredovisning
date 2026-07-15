# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class K2DuplicateWizard(models.TransientModel):
    _name = 'k2.duplicate.wizard'
    _description = 'Bekräfta duplicering av K2-årsredovisning till nästa år'

    arsredovisning_id = fields.Many2one('k2.arsredovisning', string='Årsredovisning', required=True)
    next_year = fields.Integer(string='Nästa räkenskapsår', compute='_compute_next_year')

    @api.depends('arsredovisning_id')
    def _compute_next_year(self):
        for rec in self:
            rec.next_year = (rec.arsredovisning_id.date_to.year + 1) if rec.arsredovisning_id.date_to else 0

    def action_confirm(self):
        self.ensure_one()
        return self.arsredovisning_id.action_duplicate_to_next_year()
