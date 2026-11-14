from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    zee_is_reservation = fields.Boolean(
        string="Reservation",
        copy=False,
        tracking=True,
        help="The items are kept for the customer, who pays a deposit and takes them later. "
             "Confirming the order reserves the stock, cancelling it releases the stock.",
    )
    zee_deposit_amount = fields.Monetary(
        string="Required Deposit",
        currency_field='currency_id',
        copy=False,
    )
    zee_payment_ids = fields.One2many(
        comodel_name='account.payment',
        inverse_name='zee_sale_order_id',
        string="Deposit Payments",
        readonly=True,
    )
    zee_deposit_paid = fields.Monetary(
        string="Deposit Paid",
        compute='_compute_zee_deposit',
        currency_field='currency_id',
    )
    zee_balance_due = fields.Monetary(
        string="Balance After Deposit",
        compute='_compute_zee_deposit',
        currency_field='currency_id',
    )

    _zee_deposit_amount_positive = models.Constraint(
        "CHECK (zee_deposit_amount IS NULL OR zee_deposit_amount >= 0)",
        "The required deposit cannot be negative.",
    )

    @api.depends('amount_total', 'zee_payment_ids.amount', 'zee_payment_ids.state')
    def _compute_zee_deposit(self):
        for order in self:
            payments = order.zee_payment_ids.filtered(lambda p: p.state in ('paid', 'reconciled'))
            order.zee_deposit_paid = sum(payments.mapped('amount'))
            order.zee_balance_due = order.amount_total - order.zee_deposit_paid

    def action_confirm(self):
        for order in self.filtered('zee_is_reservation'):
            if order.zee_deposit_amount > order.amount_total:
                raise UserError(self.env._(
                    "The required deposit of reservation %(name)s is higher than its total. "
                    "Lower the deposit before confirming it.",
                    name=order.name,
                ))
        return super().action_confirm()

    def action_zee_register_deposit(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Register Deposit"),
            'res_model': 'zee.reservation.deposit',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_amount': max(self.zee_deposit_amount - self.zee_deposit_paid, 0.0),
            },
        }
