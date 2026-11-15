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
            payments = order.zee_payment_ids.filtered(lambda p: p.state in ('paid', 'reconciled', 'in_process'))
            # Deposits are received (inbound), refunds are paid back (outbound).
            order.zee_deposit_paid = sum(
                p.amount if p.payment_type == 'inbound' else -p.amount for p in payments
            )
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

    def action_cancel(self):
        for order in self.filtered('zee_is_reservation'):
            if any(p.state == 'done' for p in order.picking_ids):
                raise UserError(self.env._(
                    "Reservation %s was already delivered and cannot be cancelled.", order.name,
                ))
            order._zee_refund_deposits()
        return super().action_cancel()

    def _zee_refund_deposits(self):
        """Pay back the deposits still held by the customer, in the journal they were paid in."""
        self.ensure_one()
        held = self.zee_deposit_paid
        if held <= 0:
            return
        last_deposit = self.zee_payment_ids.filtered(
            lambda p: p.payment_type == 'inbound' and p.state in ('paid', 'in_process', 'reconciled')
        ).sorted('id')[-1:]
        refund = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'amount': held,
            'currency_id': self.currency_id.id,
            'journal_id': last_deposit.journal_id.id,
            'date': fields.Date.context_today(self),
            'memo': self.env._("Refund of the deposit of %s", self.name),
            'zee_sale_order_id': self.id,
        })
        refund.action_post()
        self.message_post(body=self.env._("Deposits of %(amount)s refunded on cancellation.", amount=held))

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
