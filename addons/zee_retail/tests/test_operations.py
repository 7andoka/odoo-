from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'zee_retail')
class TestStockAudit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.shirt = cls.env['product.product'].create({
            'name': "Audit shirt", 'is_storable': True, 'barcode': '6220000000011',
        })
        cls.socks = cls.env['product.product'].create({
            'name': "Audit socks", 'is_storable': True, 'barcode': '6220000000028',
        })
        for product, qty in ((cls.shirt, 5), (cls.socks, 3)):
            quant = cls.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product.id,
                'location_id': cls.warehouse.lot_stock_id.id,
                'inventory_quantity': qty,
            })
            quant.action_apply_inventory()

    def _audit(self):
        return self.env['zee.stock.audit'].create({
            'warehouse_id': self.warehouse.id,
            'location_id': self.warehouse.lot_stock_id.id,
        })

    def test_start_takes_the_expected_quantities(self):
        audit = self._audit()
        audit.action_start()
        self.assertEqual(audit.state, 'counting')
        line = audit.line_ids.filtered(lambda l: l.product_id == self.shirt)
        self.assertEqual(line.expected_quantity, 5)
        self.assertFalse(line.counted)

    def test_scanning_counts_one_per_scan(self):
        audit = self._audit()
        audit.action_start()
        audit.barcode_scan = '6220000000011'
        audit._onchange_barcode_scan()
        audit.barcode_scan = '6220000000011'
        audit._onchange_barcode_scan()
        line = audit.line_ids.filtered(lambda l: l.product_id == self.shirt)
        self.assertTrue(line.counted)
        self.assertEqual(line.counted_quantity, 2)

    def test_unknown_barcode_adds_nothing(self):
        audit = self._audit()
        audit.action_start()
        lines_before = len(audit.line_ids)
        audit.barcode_scan = '0000000000000'
        audit._onchange_barcode_scan()
        self.assertEqual(len(audit.line_ids), lines_before)

    def test_apply_writes_the_counted_quantity(self):
        audit = self._audit()
        audit.action_start()
        audit.barcode_scan = '6220000000011'
        audit._onchange_barcode_scan()
        audit.action_apply()
        self.assertEqual(audit.state, 'done')
        qty = self.shirt.with_context(location=self.warehouse.lot_stock_id.id).qty_available
        self.assertEqual(qty, 1)

    def test_cannot_apply_before_counting(self):
        audit = self._audit()
        with self.assertRaises(UserError):
            audit.action_apply()


@tagged('post_install', '-at_install', 'zee_retail')
class TestDailyClosing(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Method = cls.env['pos.payment.method'].with_context(active_test=False)
        cls.method = Method.search([('type', '=', 'bank')], limit=1) or Method.create({
            'name': "Zee test bank", 'type': 'bank',
        })

    def test_totals_and_difference(self):
        closing = self.env['zee.daily.closing'].create({})
        self.env['zee.daily.closing.line'].create({
            'closing_id': closing.id,
            'payment_method_id': self.method.id,
            'system_amount': 1000.0,
            'counted_amount': 950.0,
            'counted': True,
        })
        self.assertEqual(closing.total_system, 1000.0)
        self.assertEqual(closing.total_counted, 950.0)
        self.assertEqual(closing.total_difference, -50.0)

    def test_cannot_close_without_sessions(self):
        closing = self.env['zee.daily.closing'].create({})
        with self.assertRaises(UserError):
            closing.action_close()

    def test_closed_day_is_locked(self):
        closing = self.env['zee.daily.closing'].create({})
        closing.state = 'closed'
        with self.assertRaises(UserError):
            closing.action_compute()


@tagged('post_install', '-at_install', 'zee_retail')
class TestReservationSettlement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': "Reservation customer"})
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', cls.env.company.id),
        ], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': "Reserved sofa", 'list_price': 1000.0, 'is_storable': True,
            'taxes_id': [Command.clear()],
        })
        quant = cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': cls.product.id,
            'location_id': cls.env['stock.warehouse'].search(
                [('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id.id,
            'inventory_quantity': 5,
        })
        quant.action_apply_inventory()

    def test_settle_collects_balance_and_delivers(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'zee_is_reservation': True,
            'zee_deposit_amount': 400.0,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        self.env['zee.reservation.deposit'].create({
            'order_id': order.id,
            'journal_id': self.journal.id,
            'amount': 400.0,
        }).action_register_deposit()
        self.assertEqual(order.zee_deposit_paid, 400.0)

        settle = self.env['zee.reservation.settle'].create({
            'order_id': order.id,
            'journal_id': self.journal.id,
        })
        self.assertEqual(settle.balance_amount, 600.0)
        settle.action_settle()

        invoice = order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice')[:1]
        self.assertEqual(invoice.payment_state, 'paid')
        self.assertEqual(order.zee_balance_due, 0.0)
