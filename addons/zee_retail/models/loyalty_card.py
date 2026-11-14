from odoo import api, models
from odoo.exceptions import AccessError


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    @api.model
    def _zee_issue_return_voucher(self, partner, amount):
        """Create a return voucher: an eWallet card of `partner` holding `amount`.

        The card is used like any eWallet in the Point of Sale and in sales orders, which
        deduct only the amount really used and keep the rest.
        """
        user = self.env.user
        if not (user.has_group('sales_team.group_sale_manager')
                or user.has_group('point_of_sale.group_pos_manager')):
            raise AccessError(self.env._("Only sales or point of sale managers can issue return vouchers."))
        program = self.env.ref('zee_retail.loyalty_program_return_voucher')
        # The managers checked above may not have the right to create cards.
        return self.sudo().create({
            'program_id': program.id,
            'partner_id': partner.id,
            'points': amount,
        })
