from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class ZeeStockAudit(models.Model):
    _name = 'zee.stock.audit'
    _description = "Stock Audit"
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
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string="Branch",
        required=True,
        check_company=True,
        tracking=True,
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        string="Location",
        required=True,
        check_company=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
        help="The audit counts every product stored in this location and its children.",
    )
    user_id = fields.Many2one(comodel_name='res.users', default=lambda self: self.env.user, readonly=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    state = fields.Selection(
        selection=[
            ('draft', "Draft"),
            ('counting', "Counting"),
            ('done', "Applied"),
            ('cancelled', "Cancelled"),
        ],
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many(comodel_name='zee.stock.audit.line', inverse_name='audit_id', copy=False)
    line_count = fields.Integer(compute='_compute_line_count')
    difference_count = fields.Integer(
        string="Lines With Difference",
        compute='_compute_line_count',
    )

    @api.depends('line_ids.difference_quantity', 'line_ids.counted')
    def _compute_line_count(self):
        for audit in self:
            audit.line_count = len(audit.line_ids)
            audit.difference_count = len(audit.line_ids.filtered(
                lambda line: line.counted and not float_is_zero(line.difference_quantity, precision_digits=4)
            ))

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id(self):
        self.location_id = self.warehouse_id.lot_stock_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._("New")) == self.env._("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('zee.stock.audit') or self.env._("New")
        return super().create(vals_list)

    def action_start(self):
        """Take the expected quantities from the system and open the count."""
        for audit in self:
            if audit.state != 'draft':
                raise UserError(self.env._("Only a draft audit can be started."))
            quants = self.env['stock.quant'].search([
                ('location_id', 'child_of', audit.location_id.id),
                ('location_id.usage', '=', 'internal'),
            ])
            grouped = {}
            for quant in quants:
                grouped[quant.product_id.id] = grouped.get(quant.product_id.id, 0.0) + quant.quantity
            audit.line_ids = [
                fields.Command.create({'product_id': product_id, 'expected_quantity': quantity})
                for product_id, quantity in grouped.items()
            ]
            audit.state = 'counting'

    def action_apply(self):
        """Write the counted quantities into the stock. Lines not counted are left untouched."""
        for audit in self:
            if audit.state != 'counting':
                raise UserError(self.env._("Only an audit being counted can be applied."))
            if not self.env.user.has_group('stock.group_stock_manager'):
                raise UserError(self.env._("Only a stock manager can apply an audit."))
            Quant = self.env['stock.quant'].with_context(inventory_mode=True)
            counted_lines = audit.line_ids.filtered('counted')
            for line in counted_lines:
                quant = Quant.search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id', '=', audit.location_id.id),
                ], limit=1)
                if not quant:
                    quant = Quant.create({
                        'product_id': line.product_id.id,
                        'location_id': audit.location_id.id,
                        'inventory_quantity': line.counted_quantity,
                    })
                else:
                    quant.inventory_quantity = line.counted_quantity
            Quant.search([
                ('location_id', '=', audit.location_id.id),
                ('inventory_quantity_set', '=', True),
            ]).action_apply_inventory()
            audit.state = 'done'
            audit.message_post(body=self.env._(
                "Audit applied: %(count)s products counted.", count=len(counted_lines)
            ))

    def action_cancel(self):
        if any(audit.state == 'done' for audit in self):
            raise UserError(self.env._("An applied audit cannot be cancelled."))
        self.state = 'cancelled'


class ZeeStockAuditLine(models.Model):
    _name = 'zee.stock.audit.line'
    _description = "Stock Audit Line"
    _order = 'audit_id, id'

    audit_id = fields.Many2one(comodel_name='zee.stock.audit', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='audit_id.company_id', store=True)
    state = fields.Selection(related='audit_id.state')
    product_id = fields.Many2one(comodel_name='product.product', required=True, string="Product")
    uom_id = fields.Many2one(related='product_id.uom_id')
    expected_quantity = fields.Float(string="Expected", digits='Product Unit', readonly=True)
    counted = fields.Boolean(string="Counted", copy=False)
    counted_quantity = fields.Float(string="Counted Qty", digits='Product Unit')
    difference_quantity = fields.Float(
        string="Difference",
        compute='_compute_difference_quantity',
        digits='Product Unit',
    )

    _product_audit_uniq = models.Constraint(
        'unique (audit_id, product_id)',
        'A product can only be counted once per audit.',
    )

    @api.depends('expected_quantity', 'counted_quantity', 'counted')
    def _compute_difference_quantity(self):
        for line in self:
            line.difference_quantity = (line.counted_quantity - line.expected_quantity) if line.counted else 0.0

    @api.onchange('counted_quantity')
    def _onchange_counted_quantity(self):
        self.counted = True
