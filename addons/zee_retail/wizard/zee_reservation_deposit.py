from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ZeeReservationDeposit(models.TransientModel):
    _name = 'zee.reservation.deposit'
    _description = "Register the deposit of a reservation"

    def _default_journal_id(self):
        return self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    order_id = fields.Many2one(comodel_name='sale.order', required=True, readonly=True)
    company_id = fields.Many2one(related='order_id.company_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        required=True,
        default=_default_journal_id,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    amount = fields.Monetary(required=True, currency_field='currency_id')
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    memo = fields.Char()

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(self.env._("The deposit must be a positive amount."))

    def action_register_deposit(self):
        """Post a customer payment linked to the reservation: it stays available as a credit
        that the final invoice of the order can use."""
        self.ensure_one()
        order = self.order_id
        if not order.zee_is_reservation:
            raise UserError(self.env._("%s is not a reservation.", order.name))
        if order.state == 'cancel':
            raise UserError(self.env._("The reservation %s is cancelled.", order.name))
        if not order.partner_id:
            raise UserError(self.env._("Set a customer on the reservation before registering a deposit."))
        if order.zee_deposit_paid + self.amount > order.amount_total:
            raise UserError(self.env._("The deposits cannot exceed the total of the reservation."))
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': order.partner_id.id,
            'amount': self.amount,
            'currency_id': order.currency_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'memo': self.memo or order.name,
            'zee_sale_order_id': order.id,
        })
        payment.action_post()
        return {'type': 'ir.actions.act_window_close'}
