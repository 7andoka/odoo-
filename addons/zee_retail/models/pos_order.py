from odoo import fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    zee_return_voucher_id = fields.Many2one(
        comodel_name='loyalty.card',
        string="Return Voucher",
        copy=False,
        readonly=True,
        index='btree_not_null',
        ondelete='set null',
    )

    def action_zee_issue_return_voucher(self):
        """Give the customer a voucher for the total of this return order."""
        self.ensure_one()
        if self.state not in ('paid', 'done') or self.amount_total >= 0:
            raise UserError(self.env._("A return voucher can only be issued for a paid return order."))
        if not self.partner_id:
            raise UserError(self.env._("Set a customer on the return order before issuing a return voucher."))
        if self.zee_return_voucher_id:
            raise UserError(self.env._("A return voucher was already issued for this order."))
        self.zee_return_voucher_id = self.env['loyalty.card']._zee_issue_return_voucher(
            self.partner_id, -self.amount_total,
        )
