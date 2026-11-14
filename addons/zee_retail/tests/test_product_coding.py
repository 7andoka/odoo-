from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.barcode import check_barcode_encoding

from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestProductCoding(BaseCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant = cls.env['res.partner'].create({'name': "Merchant", 'zee_merchant_code': '7'})
        cls.other_merchant = cls.env['res.partner'].create({'name': "Other merchant", 'zee_merchant_code': '12'})
        cls.category = cls.env['product.category'].create({'name': "T-Shirts", 'zee_category_code': 'ts'})
        cls.color = cls.env['product.attribute'].create({
            'name': "Zee Color",
            'value_ids': [
                Command.create({'name': "Black", 'zee_code': 'BL'}),
                Command.create({'name': "White", 'zee_code': 'WH'}),
            ],
        })
        cls.size = cls.env['product.attribute'].create({
            'name': "Zee Size",
            'value_ids': [
                Command.create({'name': "M", 'zee_code': 'M'}),
                Command.create({'name': "L", 'zee_code': 'L'}),
            ],
        })

    def _create_template(self, name="Shirt", merchant=None):
        return self.env['product.template'].create({
            'name': name,
            'categ_id': self.category.id,
            'zee_merchant_id': (merchant or self.merchant).id,
            'attribute_line_ids': [
                Command.create({
                    'attribute_id': self.color.id,
                    'value_ids': [Command.set(self.color.value_ids.ids)],
                }),
                Command.create({
                    'attribute_id': self.size.id,
                    'value_ids': [Command.set(self.size.value_ids.ids)],
                }),
            ],
        })

    def test_codes_are_normalized(self):
        self.assertEqual(self.merchant.zee_merchant_code, '07')
        self.assertEqual(self.category.zee_category_code, 'TS')

    def test_invalid_codes(self):
        with self.assertRaises(ValidationError):
            self.merchant.zee_merchant_code = 'AB'
        with self.assertRaises(ValidationError):
            self.category.zee_category_code = '1A'

    def test_base_code_and_variant_codes(self):
        template = self._create_template()
        self.assertEqual(template.zee_base_code, 'TS070001')
        codes = set(template.product_variant_ids.mapped('default_code'))
        self.assertEqual(codes, {
            'TS070001-BLM', 'TS070001-BLL', 'TS070001-WHM', 'TS070001-WHL',
        })

    def test_serial_is_never_reused_and_is_per_merchant(self):
        first = self._create_template("First")
        second = self._create_template("Second")
        other = self._create_template("Other", merchant=self.other_merchant)
        self.assertEqual(first.zee_base_code, 'TS070001')
        self.assertEqual(second.zee_base_code, 'TS070002')
        self.assertEqual(other.zee_base_code, 'TS120001')
        first.unlink()
        third = self._create_template("Third")
        self.assertEqual(third.zee_base_code, 'TS070003')

    def test_barcodes_are_valid_unique_ean13(self):
        template = self._create_template()
        barcodes = template.product_variant_ids.mapped('barcode')
        self.assertEqual(len(set(barcodes)), 4)
        for barcode in barcodes:
            self.assertTrue(barcode.startswith('622'))
            self.assertTrue(check_barcode_encoding(barcode, 'ean13'))

    def test_existing_values_are_kept(self):
        product = self.env['product.template'].create({
            'name': "Manual",
            'categ_id': self.category.id,
            'default_code': 'MANUAL',
            'barcode': '4006381333931',
        })
        product.zee_merchant_id = self.merchant
        variant = product.product_variant_id
        self.assertTrue(product.zee_base_code)
        self.assertEqual(variant.default_code, 'MANUAL')
        self.assertEqual(variant.barcode, '4006381333931')

    def test_code_is_assigned_when_merchant_is_set_later(self):
        product = self.env['product.template'].create({'name': "Later", 'categ_id': self.category.id})
        self.assertFalse(product.zee_base_code)
        product.zee_merchant_id = self.merchant
        self.assertEqual(product.zee_base_code, 'TS070001')
        self.assertEqual(product.product_variant_id.default_code, 'TS070001')
