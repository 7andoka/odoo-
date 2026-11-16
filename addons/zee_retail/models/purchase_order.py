from odoo import models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        res = super().button_confirm()
        # Zee-erp2 builds the item code from the supplier code when the product has no merchant.
        for order in self:
            merchant = order.partner_id
            if not merchant.zee_merchant_code:
                continue
            templates = order.order_line.product_id.product_tmpl_id.filtered(lambda t: not t.zee_merchant_id)
            templates.zee_merchant_id = merchant
        return res
