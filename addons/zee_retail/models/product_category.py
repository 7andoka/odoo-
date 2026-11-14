import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = 'product.category'

    zee_category_code = fields.Char(
        string="Item Code Prefix",
        copy=False,
        help="Letters (1 to 4) that start the item code of the products of this category, e.g. TS.",
    )

    @api.constrains('zee_category_code')
    def _check_zee_category_code(self):
        for category in self:
            code = category.zee_category_code
            if code and not re.fullmatch(r'[A-Z]{1,4}', code):
                raise ValidationError(self.env._(
                    "The item code prefix of %s must contain between 1 and 4 letters.",
                    category.display_name,
                ))

    @api.model
    def _zee_normalize_category_code(self, code):
        return (code or '').strip().upper() or False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'zee_category_code' in vals:
                vals['zee_category_code'] = self._zee_normalize_category_code(vals['zee_category_code'])
        return super().create(vals_list)

    def write(self, vals):
        if 'zee_category_code' in vals:
            vals = dict(vals, zee_category_code=self._zee_normalize_category_code(vals['zee_category_code']))
        return super().write(vals)
