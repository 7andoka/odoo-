from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ZeeReservationSettle(models.TransientModel):
    _name = 'zee.reservation.settle'
    _description = "Settle Reservation"

    order_id = fields.Many2one(comodel_name='sale.order', required=True, readonly=True)
    company_id = fields.Many2one(related='order_id.company_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    deposit_paid = fields.Monetary(related='order_id.zee_deposit_paid', currency_field='currency_id')
    balance_amount = fields.Monetary(
        string="Balance to Collect",
        currency_field='currency_id',
        compute='_compute_balance_amount',
        readonly=False,
        store=True,
        help="What the customer pays now, on top of the deposits already taken.",
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string="Journal",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    payment_date = fields.Date(default=fields.Date.context_today, required=True)

    @api.depends('order_id')
    def _compute_balance_amount(self):
        for wizard in self:
            wizard.balance_amount = max(wizard.order_id.zee_balance_due, 0.0)

    @api.constrains('balance_amount')
    def _check_balance_amount(self):
        for wizard in self:
            if wizard.balance_amount < 0:
                raise ValidationError(self.env._("The balance to collect cannot be negative."))

    def action_settle(self):
        """Collect the balance, reconcile the deposits and the balance with the invoice,
        then deliver the reserved products."""
        self.ensure_one()
        order = self.order_id
        if not order.zee_is_reservation:
            raise UserError(self.env._("%s is not a reservation.", order.name))
        if order.state != 'sale':
            raise UserError(self.env._("The reservation %s must be confirmed before it is settled.", order.name))
        if self.balance_amount > 0 and not self.journal_id:
            raise UserError(self.env._("Choose the journal that receives the balance."))

        invoice = order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')[:1]
        if not invoice:
            invoice = order._create_invoices()[:1]
            invoice.action_post()

        deposits = order.zee_payment_ids.filtered(lambda p: p.state in ('paid', 'in_process', 'reconciled'))
        self._zee_reconcile(invoice, deposits)

        if self.balance_amount > 0:
            balance_payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': order.partner_id.id,
                'amount': self.balance_amount,
                'currency_id': order.currency_id.id,
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'memo': order.name,
                'zee_sale_order_id': order.id,
            })
            balance_payment.action_post()
            self._zee_reconcile(invoice, balance_payment)

        self._zee_deliver(order)
        order.message_post(body=self.env._("Reservation settled and delivered."))
        return {'type': 'ir.actions.act_window_close'}

    def _zee_reconcile(self, invoice, payments):
        receivable = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )
        for payment in payments:
            lines = (receivable + payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            ))
            if lines:
                lines.reconcile()

    def _zee_deliver(self, order):
        pickings = order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        for picking in pickings:
            picking.action_confirm()
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(skip_backorder=True, skip_sanity_check=True).button_validate()
