from odoo import fields, models


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    zee_code = fields.Char(
        string="Item Code",
        help="Short code added to the item code of the variants that use this value, e.g. BL for Black.",
    )
