from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    zee_sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string="Reservation",
        copy=False,
        readonly=True,
        index='btree_not_null',
        ondelete='set null',
    )
