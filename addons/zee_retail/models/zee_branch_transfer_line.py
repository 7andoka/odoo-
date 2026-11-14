from odoo import api, fields, models


class ZeeBranchTransferLine(models.Model):
    _name = 'zee.branch.transfer.line'
    _description = "Branch Transfer Line"
    _order = 'transfer_id, id'

    transfer_id = fields.Many2one(
        comodel_name='zee.branch.transfer',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(related='transfer_id.company_id', store=True)
    state = fields.Selection(related='transfer_id.state')
    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Product",
        required=True,
        domain="[('is_storable', '=', True)]",
    )
    uom_id = fields.Many2one(related='product_id.uom_id')
    quantity = fields.Float(required=True, default=1.0, digits='Product Unit')
    received_quantity = fields.Float(copy=False, digits='Product Unit')
    available_quantity = fields.Float(
        string="Available at Source",
        compute='_compute_available_quantity',
        digits='Product Unit',
    )
    is_negative = fields.Boolean(
        string="Exceeds Stock",
        compute='_compute_available_quantity',
    )

    _product_uniq = models.Constraint(
        'unique (transfer_id, product_id)',
        'A product can only appear once in a transfer.',
    )
    _quantity_positive = models.Constraint(
        'CHECK (quantity > 0)',
        'The quantity to transfer must be positive.',
    )
    _received_quantity_valid = models.Constraint(
        'CHECK (received_quantity >= 0 AND received_quantity <= quantity)',
        'The received quantity must be between zero and the quantity sent.',
    )

    @api.depends('product_id', 'quantity', 'transfer_id.source_warehouse_id', 'transfer_id.state')
    def _compute_available_quantity(self):
        for transfer, lines in self.grouped('transfer_id').items():
            location = transfer.source_warehouse_id.lot_stock_id
            if not location or transfer.state != 'requested':
                lines.available_quantity = 0.0
                lines.is_negative = False
                continue
            products = lines.product_id.with_context(location=location.id)
            free_quantities = {product.id: product.free_qty for product in products}
            for line in lines:
                available = free_quantities.get(line.product_id.id, 0.0)
                line.available_quantity = available
                line.is_negative = line.quantity > available
