from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'zee_retail')
class TestPurchaseFlow(TransactionCase):
    """Purchases: a purchase order is received into the stock of the branch."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.supplier = cls.env['res.partner'].create({'name': 'Zee Supplier', 'supplier_rank': 1, 'zee_merchant_code': '03'})
        cls.product = cls.env['product.product'].create({
            'name': 'Test shirt',
            'is_storable': True,
            'standard_price': 10.0,
        })

    def test_purchase_receipt_increases_stock(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_qty': 5,
                'price_unit': 10.0,
            })],
        })
        order.button_confirm()
        receipt = order.picking_ids
        self.assertEqual(len(receipt), 1)
        for move in receipt.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        receipt.with_context(skip_backorder=True, skip_sanity_check=True).button_validate()
        self.assertEqual(receipt.state, 'done')
        qty = self.product.with_context(location=self.warehouse.lot_stock_id.id).qty_available
        self.assertGreaterEqual(qty, 5)

    def test_vendor_bill_can_be_created_from_purchase(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.supplier.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_qty': 2,
                'price_unit': 10.0,
            })],
        })
        order.button_confirm()
        order.action_create_invoice()
        self.assertTrue(order.invoice_ids)
        self.assertEqual(order.invoice_ids[0].move_type, 'in_invoice')


@tagged('post_install', '-at_install', 'zee_retail')
class TestBranchTransferFlow(TransactionCase):
    """Branch transfers: goods leave one branch and arrive at the other."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.branch_a = cls.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        cls.branch_b = cls.env['stock.warehouse'].create({
            'name': 'Branch B', 'code': 'BRB', 'company_id': company.id,
        })
        cls.product = cls.env['product.product'].create({'name': 'Transfer shirt', 'is_storable': True})
        quant = cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': cls.product.id,
            'location_id': cls.branch_a.lot_stock_id.id,
            'inventory_quantity': 10,
        })
        quant.action_apply_inventory()

    def _new_transfer(self, qty):
        return self.env['zee.branch.transfer'].create({
            'source_warehouse_id': self.branch_a.id,
            'dest_warehouse_id': self.branch_b.id,
            'line_ids': [Command.create({'product_id': self.product.id, 'quantity': qty})],
        })

    def test_dispatch_then_receive(self):
        transfer = self._new_transfer(4)
        transfer.action_dispatch()
        self.assertEqual(transfer.state, 'dispatched')
        transfer.action_receive()
        self.assertEqual(transfer.state, 'received')
        at_b = self.product.with_context(location=self.branch_b.lot_stock_id.id).qty_available
        self.assertEqual(at_b, 4)

    def test_cannot_receive_before_dispatch(self):
        transfer = self._new_transfer(1)
        with self.assertRaises(UserError):
            transfer.action_receive()

    def test_source_and_destination_must_differ(self):
        with self.assertRaises(ValidationError):
            self.env['zee.branch.transfer'].create({
                'source_warehouse_id': self.branch_a.id,
                'dest_warehouse_id': self.branch_a.id,
                'line_ids': [Command.create({'product_id': self.product.id, 'quantity': 1})],
            })


@tagged('post_install', '-at_install', 'zee_retail')
class TestEmployeeAdvance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Zee Employee'})

    def _paid_advance(self, amount):
        advance = self.env['zee.employee.advance'].create({
            'employee_id': self.employee.id, 'amount': amount,
        })
        advance.action_approve()
        advance.action_pay()
        return advance

    def test_repayments_cannot_exceed_the_advance(self):
        advance = self._paid_advance(100)
        self.env['zee.employee.advance.repayment'].create({'advance_id': advance.id, 'amount': 60})
        self.assertEqual(advance.balance, 40)
        with self.assertRaises(UserError):
            self.env['zee.employee.advance.repayment'].create({'advance_id': advance.id, 'amount': 50})

    def test_advance_must_be_approved_before_payment(self):
        advance = self.env['zee.employee.advance'].create({'employee_id': self.employee.id, 'amount': 10})
        with self.assertRaises(UserError):
            advance.action_pay()


@tagged('post_install', '-at_install', 'zee_retail')
class TestPurchaseMerchantLink(TransactionCase):
    """A product bought from a merchant takes that merchant, and its item code follows."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant = cls.env['res.partner'].create({'name': 'Merchant Co', 'zee_merchant_code': '12'})
        cls.category = cls.env['product.category'].create({'name': 'Jackets', 'zee_category_code': 'JK'})

    def test_confirmed_purchase_sets_the_merchant_and_item_code(self):
        product = self.env['product.template'].create({
            'name': 'Jacket', 'categ_id': self.category.id, 'is_storable': True,
        })
        self.assertFalse(product.zee_base_code)
        order = self.env['purchase.order'].create({
            'partner_id': self.merchant.id,
            'order_line': [Command.create({
                'product_id': product.product_variant_id.id, 'product_qty': 1, 'price_unit': 50.0,
            })],
        })
        order.button_confirm()
        self.assertEqual(product.zee_merchant_id, self.merchant)
        self.assertTrue(product.zee_base_code.startswith('JK12'))

    def test_existing_merchant_is_kept(self):
        other = self.env['res.partner'].create({'name': 'Other Co', 'zee_merchant_code': '13'})
        product = self.env['product.template'].create({
            'name': 'Kept jacket', 'categ_id': self.category.id, 'zee_merchant_id': other.id,
            'is_storable': True,
        })
        order = self.env['purchase.order'].create({
            'partner_id': self.merchant.id,
            'order_line': [Command.create({
                'product_id': product.product_variant_id.id, 'product_qty': 1, 'price_unit': 50.0,
            })],
        })
        order.button_confirm()
        self.assertEqual(product.zee_merchant_id, other)

    def test_supplier_without_merchant_code_cannot_be_confirmed(self):
        supplier = self.env['res.partner'].create({'name': 'No code supplier'})
        product = self.env['product.template'].create({'name': 'Blocked', 'is_storable': True})
        order = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'order_line': [Command.create({
                'product_id': product.product_variant_id.id, 'product_qty': 1, 'price_unit': 5.0,
            })],
        })
        with self.assertRaises(UserError):
            order.button_confirm()
