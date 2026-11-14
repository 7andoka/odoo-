from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class ZeeBranchTransfer(models.Model):
    _name = 'zee.branch.transfer'
    _description = "Branch Transfer"
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
    state = fields.Selection(
        selection=[
            ('requested', "Requested"),
            ('dispatched', "In Transit"),
            ('received', "Received"),
            ('cancelled', "Cancelled"),
        ],
        required=True,
        default='requested',
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
    )
    source_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string="From",
        required=True,
        check_company=True,
        tracking=True,
        index=True,
    )
    dest_warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string="To",
        required=True,
        check_company=True,
        tracking=True,
        index=True,
    )
    line_ids = fields.One2many(
        comodel_name='zee.branch.transfer.line',
        inverse_name='transfer_id',
        string="Products",
        copy=True,
    )
    note = fields.Text()
    total_quantity = fields.Float(compute='_compute_total_quantity', store=True, digits='Product Unit')
    has_negative_stock = fields.Boolean(
        compute='_compute_has_negative_stock',
        help="The source does not hold enough stock for at least one line.",
    )
    dispatch_picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Dispatch Transfer",
        copy=False,
        readonly=True,
        index='btree_not_null',
    )
    receive_picking_id = fields.Many2one(
        comodel_name='stock.picking',
        string="Receipt Transfer",
        copy=False,
        readonly=True,
        index='btree_not_null',
    )
    dispatched_by_id = fields.Many2one(comodel_name='res.users', copy=False, readonly=True)
    dispatched_at = fields.Datetime(copy=False, readonly=True)
    received_by_id = fields.Many2one(comodel_name='res.users', copy=False, readonly=True)
    received_at = fields.Datetime(copy=False, readonly=True)

    @api.constrains('source_warehouse_id', 'dest_warehouse_id')
    def _check_warehouses(self):
        for transfer in self:
            if transfer.source_warehouse_id == transfer.dest_warehouse_id:
                raise ValidationError(self.env._("The source and the destination of a transfer must be different."))

    @api.depends('line_ids.quantity')
    def _compute_total_quantity(self):
        for transfer in self:
            transfer.total_quantity = sum(transfer.line_ids.mapped('quantity'))

    @api.depends('line_ids.is_negative')
    def _compute_has_negative_stock(self):
        for transfer in self:
            transfer.has_negative_stock = any(transfer.line_ids.mapped('is_negative'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._("New")) == self.env._("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('zee.branch.transfer') or self.env._("New")
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_processed(self):
        if any(transfer.state in ('dispatched', 'received') for transfer in self):
            raise UserError(self.env._("A transfer that left its branch cannot be deleted."))

    def action_dispatch(self):
        """Take the goods out of the source branch: they wait in the transit location."""
        for transfer in self:
            if transfer.state != 'requested':
                raise UserError(self.env._("Only a requested transfer can be dispatched."))
            if not transfer.line_ids:
                raise UserError(self.env._("Add at least one product to %s.", transfer.name))
            picking = transfer._zee_create_picking(
                transfer.source_warehouse_id,
                transfer.source_warehouse_id.lot_stock_id,
                transfer._zee_get_transit_location(),
                [(line.product_id, line.quantity) for line in transfer.line_ids],
            )
            transfer._zee_process_picking(picking)
            for line in transfer.line_ids:
                # The receiver counts what really arrived: by default everything.
                line.received_quantity = line.quantity
            transfer.write({
                'state': 'dispatched',
                'dispatch_picking_id': picking.id,
                'dispatched_by_id': self.env.user.id,
                'dispatched_at': fields.Datetime.now(),
            })

    def action_receive(self):
        """Put the goods counted by the receiver in the stock of the destination branch."""
        for transfer in self:
            if transfer.state != 'dispatched':
                raise UserError(self.env._("Only a transfer in transit can be received."))
            picking = self.env['stock.picking']
            to_receive = [
                (line.product_id, line.received_quantity)
                for line in transfer.line_ids
                if line.received_quantity > 0
            ]
            if to_receive:
                picking = transfer._zee_create_picking(
                    transfer.dest_warehouse_id,
                    transfer._zee_get_transit_location(),
                    transfer.dest_warehouse_id.lot_stock_id,
                    to_receive,
                )
                transfer._zee_process_picking(picking)
            transfer.write({
                'state': 'received',
                'receive_picking_id': picking.id,
                'received_by_id': self.env.user.id,
                'received_at': fields.Datetime.now(),
            })
            missing = transfer.line_ids.filtered(lambda line: line.received_quantity < line.quantity)
            if missing:
                transfer.message_post(body=self.env._(
                    "Quantities missing at reception, they stay in the transit location: %s",
                    ", ".join(
                        f"{line.product_id.display_name} ({line.quantity - line.received_quantity:g})"
                        for line in missing
                    ),
                ))

    def action_cancel(self):
        for transfer in self:
            if transfer.state != 'requested':
                raise UserError(self.env._("Only a requested transfer can be cancelled."))
        self.write({'state': 'cancelled'})

    def _zee_get_transit_location(self):
        self.ensure_one()
        return self.env.ref('zee_retail.stock_location_zee_transit')

    def _zee_create_picking(self, warehouse, location, location_dest, product_quantities):
        """Create the stock transfer that moves `product_quantities` from `location` to `location_dest`.

        :param product_quantities: list of `(product, quantity)`
        """
        self.ensure_one()
        picking_type = warehouse.int_type_id
        return self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': location.id,
            'location_dest_id': location_dest.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'move_ids': [
                Command.create({
                    'product_id': product.id,
                    'uom_id': product.uom_id.id,
                    'product_uom_qty': quantity,
                    'location_id': location.id,
                    'location_dest_id': location_dest.id,
                    'picking_type_id': picking_type.id,
                })
                for product, quantity in product_quantities
            ],
        })

    def _zee_process_picking(self, picking):
        """Validate the whole quantity of a stock transfer, even without enough reserved stock."""
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_backorder=True, skip_sanity_check=True).button_validate()
        if picking.state != 'done':
            raise UserError(self.env._("The stock transfer %s could not be validated.", picking.name))
