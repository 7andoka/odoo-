from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    zee_merchant_id = fields.Many2one(
        comodel_name='res.partner',
        string="Merchant",
        domain="[('zee_merchant_code', '!=', False)]",
        index='btree_not_null',
        help="Merchant supplying this item. With a category item code prefix, it triggers "
             "the automatic item code.",
    )
    zee_base_code = fields.Char(
        string="Item Base Code",
        copy=False,
        readonly=True,
        index='btree_not_null',
        help="Category prefix, merchant code and serial. The variants add their attribute codes.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._zee_assign_base_code()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if 'zee_merchant_id' in vals or 'categ_id' in vals:
            self._zee_assign_base_code()
        return res

    def _zee_assign_base_code(self):
        """Give a base code to the templates that can have one, then code their variants."""
        for template in self:
            if template.zee_base_code:
                continue
            prefix = template.categ_id.zee_category_code
            merchant = template.zee_merchant_id
            if not prefix or not merchant:
                continue
            # Zee-erp2 uses exactly two letters for the category, padded with X.
            letters = prefix[:2].ljust(2, 'X')
            template.zee_base_code = f"{letters}{merchant.zee_merchant_code}{merchant._zee_next_serial()}"
        self.product_variant_ids._zee_assign_codes()
