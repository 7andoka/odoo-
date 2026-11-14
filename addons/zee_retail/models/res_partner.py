import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    zee_merchant_code = fields.Char(
        string="Merchant Code",
        copy=False,
        help="Numeric code (2 to 6 digits) of the merchant, used to build the item codes "
             "of the products supplied by this contact.",
    )
    zee_last_serial = fields.Integer(
        string="Last Item Serial",
        copy=False,
        readonly=True,
        help="Last serial given to an item of this merchant. A serial is never reused.",
    )

    _zee_merchant_code_uniq = models.UniqueIndex(
        "(zee_merchant_code) WHERE (zee_merchant_code IS NOT NULL)",
        "This merchant code is already used by another contact.",
    )

    @api.constrains('zee_merchant_code')
    def _check_zee_merchant_code(self):
        for partner in self:
            code = partner.zee_merchant_code
            if code and not re.fullmatch(r'\d{2,6}', code):
                raise ValidationError(self.env._(
                    "The merchant code of %s must contain between 2 and 6 digits.",
                    partner.display_name,
                ))

    @api.model
    def _zee_normalize_merchant_code(self, code):
        code = (code or '').strip()
        if not code:
            return False
        if len(code) == 1 and code.isdigit():
            return code.zfill(2)
        return code

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'zee_merchant_code' in vals:
                vals['zee_merchant_code'] = self._zee_normalize_merchant_code(vals['zee_merchant_code'])
        return super().create(vals_list)

    def write(self, vals):
        if 'zee_merchant_code' in vals:
            vals = dict(vals, zee_merchant_code=self._zee_normalize_merchant_code(vals['zee_merchant_code']))
        return super().write(vals)

    def _zee_next_serial(self):
        """Return the next item serial of this merchant, as a 4 digits string."""
        self.ensure_one()
        # Whoever creates a product must be able to take a serial, whatever its rights on contacts.
        merchant = self.sudo()
        merchant.lock_for_update()
        merchant.invalidate_recordset(['zee_last_serial'])
        serial = merchant.zee_last_serial + 1
        if serial > 9999:
            raise UserError(self.env._(
                "The merchant %s has no serial left (the maximum is 9999).", merchant.display_name,
            ))
        merchant.zee_last_serial = serial
        return f"{serial:04d}"
