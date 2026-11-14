from odoo import api, fields, models
from odoo.exceptions import UserError


class ZeeDailyClosing(models.Model):
    _name = 'zee.daily.closing'
    _description = "Daily Closing"
    _inherit = ['mail.thread']
    _check_company_auto = True
    _order = 'date desc, id desc'

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env._("New"),
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    user_id = fields.Many2one(comodel_name='res.users', default=lambda self: self.env.user, readonly=True)
    session_ids = fields.Many2many(
        comodel_name='pos.session',
        string="POS Sessions",
        check_company=True,
        domain="[('company_id', '=', company_id)]",
        help="Sessions closed for the day. Their payments are summed per payment method.",
    )
    state = fields.Selection(
        selection=[('draft', "Draft"), ('closed', "Closed")],
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many(comodel_name='zee.daily.closing.line', inverse_name='closing_id', copy=False)
    total_system = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    total_counted = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')
    total_difference = fields.Monetary(compute='_compute_totals', store=True, currency_field='currency_id')

    _date_company_uniq = models.Constraint(
        'unique (company_id, date)',
        'There is already a closing for this day.',
    )

    @api.depends('line_ids.system_amount', 'line_ids.counted_amount')
    def _compute_totals(self):
        for closing in self:
            closing.total_system = sum(closing.line_ids.mapped('system_amount'))
            closing.total_counted = sum(closing.line_ids.mapped('counted_amount'))
            closing.total_difference = closing.total_counted - closing.total_system

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._("New")) == self.env._("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('zee.daily.closing') or self.env._("New")
        return super().create(vals_list)

    def action_compute(self):
        """Refresh the system amount of every payment method from the payments of the sessions."""
        Payment = self.env['pos.payment']
        for closing in self:
            self._check_editable(closing)
            payments = Payment.search([
                ('pos_order_id.session_id', 'in', closing.session_ids.ids),
                ('pos_order_id.state', 'in', ('paid', 'done', 'invoiced')),
            ])
            totals = {}
            for payment in payments:
                totals[payment.payment_method_id.id] = totals.get(payment.payment_method_id.id, 0.0) + payment.amount
            existing = {line.payment_method_id.id: line for line in closing.line_ids}
            for method_id, amount in totals.items():
                if method_id in existing:
                    existing[method_id].system_amount = amount
                else:
                    closing.line_ids = [fields.Command.create({
                        'payment_method_id': method_id,
                        'system_amount': amount,
                    })]
            closing.line_ids.filtered(
                lambda line: line.payment_method_id.id not in totals
            ).system_amount = 0.0

    def action_close(self):
        for closing in self:
            self._check_editable(closing)
            if not closing.session_ids:
                raise UserError(self.env._("Select at least one POS session before closing the day."))
            if any(not line.counted for line in closing.line_ids):
                raise UserError(self.env._("Count every payment method before closing the day."))
            closing.state = 'closed'

    def _check_editable(self, closing):
        if closing.state == 'closed':
            raise UserError(self.env._("A closed day cannot be changed."))


class ZeeDailyClosingLine(models.Model):
    _name = 'zee.daily.closing.line'
    _description = "Daily Closing Line"
    _order = 'closing_id, id'

    closing_id = fields.Many2one(comodel_name='zee.daily.closing', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='closing_id.company_id', store=True)
    currency_id = fields.Many2one(related='closing_id.currency_id')
    payment_method_id = fields.Many2one(comodel_name='pos.payment.method', string="Payment Method", required=True)
    system_amount = fields.Monetary(string="System", currency_field='currency_id', readonly=True)
    counted_amount = fields.Monetary(string="Counted", currency_field='currency_id')
    counted = fields.Boolean(string="Counted", copy=False)
    difference = fields.Monetary(
        compute='_compute_difference',
        store=True,
        currency_field='currency_id',
    )

    _method_uniq = models.Constraint(
        'unique (closing_id, payment_method_id)',
        'A payment method can only appear once per day.',
    )

    @api.depends('system_amount', 'counted_amount', 'counted')
    def _compute_difference(self):
        for line in self:
            line.difference = (line.counted_amount - line.system_amount) if line.counted else 0.0

    @api.onchange('counted_amount')
    def _onchange_counted_amount(self):
        self.counted = True
