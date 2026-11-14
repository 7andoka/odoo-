from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    zee_is_seller = fields.Boolean(string="Seller")
    zee_seller_code = fields.Char(string="Seller Code", copy=False)
    zee_is_branch_manager = fields.Boolean(
        string="Branch Manager",
        help="A branch manager is left out when a target is distributed between the sellers.",
    )
    zee_join_date = fields.Date(
        string="Seller Start Date",
        help="Used to prorate the monthly target of a seller who joined during the month.",
    )
    zee_commission_rate = fields.Float(string="Commission Rate (%)", digits=(5, 2))
    zee_monthly_target = fields.Float(string="Monthly Target")
    zee_month_sales = fields.Float(string="Month Sales", compute='_compute_zee_month_stats')
    zee_target_achievement = fields.Float(
        string="Target Achievement (%)", compute='_compute_zee_month_stats', digits=(5, 1),
    )
    zee_remaining_target = fields.Float(string="Remaining Target", compute='_compute_zee_month_stats')
    zee_estimated_commission = fields.Float(string="Estimated Commission", compute='_compute_zee_month_stats')

    @api.constrains('zee_seller_code')
    def _check_zee_seller_code(self):
        for employee in self.filtered('zee_seller_code'):
            duplicate = self.search_count([
                ('zee_seller_code', '=', employee.zee_seller_code),
                ('id', '!=', employee.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(self.env._(
                    "The seller code %s is already used by another employee.", employee.zee_seller_code,
                ))

    @api.depends('zee_monthly_target', 'zee_commission_rate')
    @api.depends_context('zee_stats_month')
    def _compute_zee_month_stats(self):
        month_start = self._zee_get_month_start()
        sales = self._zee_get_sales(month_start, month_start + relativedelta(months=1))
        for employee in self:
            total = sales.get(employee.id, 0.0)
            target = employee.zee_monthly_target
            employee.zee_month_sales = total
            if target > 0:
                employee.zee_target_achievement = round(total / target * 100, 1)
            else:
                employee.zee_target_achievement = 100.0 if total > 0 else 0.0
            employee.zee_remaining_target = max(target - total, 0.0)
            employee.zee_estimated_commission = total * employee.zee_commission_rate / 100

    @api.model
    def _zee_get_month_start(self):
        """First day of the month to report: the `zee_stats_month` context date, else this month."""
        day = fields.Date.to_date(self.env.context.get('zee_stats_month')) or fields.Date.context_today(self)
        return day.replace(day=1)

    def _zee_get_sales(self, date_start, date_end):
        """Return `{employee id: sales total}` between the two dates (end excluded).

        The sales are the paid Point of Sale orders of the employee (returns count negative)
        and the confirmed sales orders of the user of the employee.
        """
        start = fields.Datetime.to_datetime(date_start)
        end = fields.Datetime.to_datetime(date_end)
        totals = dict.fromkeys(self.ids, 0.0)
        # Reading the totals must not depend on the rights of the reader on orders.
        pos_groups = self.env['pos.order'].sudo()._read_group(
            [
                ('employee_id', 'in', self.ids),
                ('state', 'in', ('paid', 'done')),
                ('date_order', '>=', start),
                ('date_order', '<', end),
            ],
            ['employee_id'],
            ['amount_total:sum'],
        )
        for employee, amount in pos_groups:
            totals[employee.id] += amount
        employee_by_user = {employee.user_id.id: employee.id for employee in self if employee.user_id}
        if employee_by_user:
            sale_groups = self.env['sale.order'].sudo()._read_group(
                [
                    ('user_id', 'in', list(employee_by_user)),
                    ('state', '=', 'sale'),
                    ('date_order', '>=', start),
                    ('date_order', '<', end),
                ],
                ['user_id'],
                ['amount_total:sum'],
            )
            for user, amount in sale_groups:
                totals[employee_by_user[user.id]] += amount
        return totals
