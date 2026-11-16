from odoo import models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        # The supplier is the merchant of the items: its code is needed to build their item codes.
        for order in self:
            if not order.partner_id.zee_merchant_code:
                raise UserError(order.env._(
                    "The supplier %s has no merchant code. Set it before confirming the purchase.",
                    order.partner_id.display_name,
                ))
        res = super().button_confirm()
        # Zee-erp2 builds the item code from the supplier code when the product has no merchant.
        for order in self:
            merchant = order.partner_id
            if not merchant.zee_merchant_code:
                continue
            templates = order.order_line.product_id.product_tmpl_id.filtered(lambda t: not t.zee_merchant_id)
            templates.zee_merchant_id = merchant
        return res
