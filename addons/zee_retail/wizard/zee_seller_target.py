from odoo import fields, models
from odoo.exceptions import UserError

from ..tools.seller_target import active_days_ratio, distribute_target


class ZeeSellerTarget(models.TransientModel):
    _name = 'zee.seller.target'
    _description = "Distribute a sales target between sellers"

    def _default_seller_ids(self):
        return self.env['hr.employee'].search([
            ('zee_is_seller', '=', True),
            ('zee_is_branch_manager', '=', False),
        ])

    month = fields.Date(
        string="Month",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    total_target = fields.Float(string="Total Target", required=True)
    method = fields.Selection(
        selection=[
            ('prorated', "Prorated by active days"),
            ('equal', "Equal shares"),
        ],
        required=True,
        default='prorated',
    )
    seller_ids = fields.Many2many(
        comodel_name='hr.employee',
        string="Sellers",
        default=_default_seller_ids,
        domain="[('zee_is_seller', '=', True)]",
    )

    def action_distribute(self):
        """Write each seller's share of the total as its monthly target."""
        self.ensure_one()
        if self.total_target <= 0:
            raise UserError(self.env._("The total target must be positive."))
        if not self.seller_ids:
            raise UserError(self.env._("Select the sellers that share the target."))
        ratios = [
            (seller.id, active_days_ratio(seller.zee_join_date, self.month.year, self.month.month)[2])
            for seller in self.seller_ids
        ]
        shares = distribute_target(self.total_target, ratios, self.method)
        for seller in self.seller_ids:
            seller.zee_monthly_target = shares[seller.id]
        return {'type': 'ir.actions.act_window_close'}
