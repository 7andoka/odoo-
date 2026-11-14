from odoo import api, fields, models
from odoo.exceptions import UserError


class ZeeEmployeeAdvance(models.Model):
    _name = 'zee.employee.advance'
    _description = "Employee Advance"
    _inherit = ['mail.thread']
    _check_company_auto = True
    _order = 'id desc'

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
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string="Employee",
        required=True,
        check_company=True,
        tracking=True,
    )
    date = fields.Date(default=fields.Date.context_today, required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id', tracking=True)
    monthly_deduction = fields.Monetary(
        string="Monthly Deduction",
        currency_field='currency_id',
        help="Amount taken from the salary each month until the advance is repaid.",
    )
    repayment_ids = fields.One2many(comodel_name='zee.employee.advance.repayment', inverse_name='advance_id')
    repaid_amount = fields.Monetary(compute='_compute_balance', store=True, currency_field='currency_id')
    balance = fields.Monetary(compute='_compute_balance', store=True, currency_field='currency_id')
    state = fields.Selection(
        selection=[
            ('draft', "Requested"),
            ('approved', "Approved"),
            ('paid', "Paid Out"),
            ('repaid', "Repaid"),
            ('cancelled', "Cancelled"),
        ],
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    note = fields.Text()

    @api.constrains('amount', 'monthly_deduction')
    def _check_amounts(self):
        for advance in self:
            if advance.amount <= 0:
                raise UserError(self.env._("The advance must be a positive amount."))
            if advance.monthly_deduction < 0:
                raise UserError(self.env._("The monthly deduction cannot be negative."))

    @api.depends('amount', 'repayment_ids.amount')
    def _compute_balance(self):
        for advance in self:
            advance.repaid_amount = sum(advance.repayment_ids.mapped('amount'))
            advance.balance = advance.amount - advance.repaid_amount

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._("New")) == self.env._("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('zee.employee.advance') or self.env._("New")
        return super().create(vals_list)

    def action_approve(self):
        if any(advance.state != 'draft' for advance in self):
            raise UserError(self.env._("Only a requested advance can be approved."))
        self.state = 'approved'

    def action_pay(self):
        if any(advance.state != 'approved' for advance in self):
            raise UserError(self.env._("Only an approved advance can be paid out."))
        self.state = 'paid'

    def action_cancel(self):
        if any(advance.state not in ('draft', 'approved') for advance in self):
            raise UserError(self.env._("Only a requested or approved advance can be cancelled."))
        self.state = 'cancelled'

    def action_register_repayment(self):
        """Mark the advance as repaid once the balance reaches zero."""
        for advance in self:
            if advance.state != 'paid':
                raise UserError(self.env._("Only a paid advance can be repaid."))
            if advance.balance <= 0:
                advance.state = 'repaid'


class ZeeEmployeeAdvanceRepayment(models.Model):
    _name = 'zee.employee.advance.repayment'
    _description = "Employee Advance Repayment"
    _order = 'date, id'

    advance_id = fields.Many2one(comodel_name='zee.employee.advance', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='advance_id.currency_id')
    date = fields.Date(default=fields.Date.context_today, required=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')

    @api.constrains('amount', 'advance_id')
    def _check_amount(self):
        for repayment in self:
            if repayment.amount <= 0:
                raise UserError(self.env._("A repayment must be a positive amount."))
            if repayment.advance_id.state != 'paid':
                raise UserError(self.env._("Repayments can only be recorded on a paid advance."))
            if repayment.advance_id.balance < -0.005:
                raise UserError(self.env._("Repayments exceed the advance amount."))
