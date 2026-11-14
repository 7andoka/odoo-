from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools.barcode import get_barcode_check_digit


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products._zee_assign_codes()
        return products

    def _zee_assign_codes(self):
        """Fill the missing internal reference and barcode of the variants of coded templates.

        A reference or a barcode that is already set is never changed.
        """
        for product in self:
            if not product.product_tmpl_id.zee_base_code:
                continue
            values = {}
            if not product.default_code:
                values['default_code'] = product._zee_get_default_code()
            if not product.barcode:
                values['barcode'] = product._zee_generate_barcode()
            if values:
                product.write(values)

    COLOR_KEYWORDS = ('color', 'colour', 'لون')
    SIZE_KEYWORDS = ('size', 'مقاس')
    SIZE_VALUES = {'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '28', '30', '32', '34', '36', '38', '40', '42', '44', '46', '48', '50'}

    def _zee_get_default_code(self):
        """Build the variant code the way Zee-erp2 does: `<base>-<attribute codes>`.

        - color and size: the color code on 2 digits, then the size code as is (e.g. 01 + 2 = 012)
        - size only: 01 + size code; color only: color code on 2 digits + 1
        - other attributes: each code on 2 digits, the size code as is
        - no attribute: 011
        """
        self.ensure_one()
        base_code = self.product_tmpl_id.zee_base_code
        ptavs = self.product_template_variant_value_ids.sorted(
            lambda ptav: (ptav.attribute_line_id.sequence, ptav.attribute_line_id.id),
        )
        color = size = None
        others = []
        for ptav in ptavs:
            value = ptav.product_attribute_value_id
            attr_name = (ptav.attribute_id.name or '').lower()
            value_name = (value.name or '').strip()
            code = self._zee_int_code(value.zee_code, default=1)
            if any(k in attr_name for k in self.COLOR_KEYWORDS) and color is None:
                color = code
            elif (any(k in attr_name for k in self.SIZE_KEYWORDS) or value_name.upper() in self.SIZE_VALUES) and size is None:
                size = code
            else:
                others.append(code)

        if color is not None and size is not None:
            attr_codes = f"{color:02d}{size}"
        elif size is not None:
            attr_codes = f"01{size}"
        elif color is not None:
            attr_codes = f"{color:02d}1"
        elif others:
            attr_codes = ''.join(f"{code:02d}" for code in others)
        else:
            attr_codes = '011'
        return f"{base_code}-{attr_codes}"

    @api.model
    def _zee_int_code(self, code, default):
        try:
            return int(code) if code else default
        except (TypeError, ValueError):
            return default

    def _zee_generate_barcode(self):
        """Return a new EAN-13 barcode: the 12 digits of the sequence and the check digit."""
        number = self.env['ir.sequence'].sudo().next_by_code('zee.product.barcode')
        if not number:
            raise UserError(self.env._("The sequence of the Zee product barcodes is missing."))
        return f"{number}{get_barcode_check_digit(number + '0')}"
