from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestReservation(BaseCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': "Reserved item",
            'list_price': 1000.0,
            'is_storable': True,
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        cls.reservation = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'zee_is_reservation': True,
            'zee_deposit_amount': 400.0,
            'order_line': [Command.create({'product_id': cls.product.id, 'product_uom_qty': 1})],
        })

    def _register(self, amount):
        wizard = self.env['zee.reservation.deposit'].create({
            'order_id': self.reservation.id,
            'journal_id': self.journal.id,
            'amount': amount,
        })
        wizard.action_register_deposit()

    def test_deposit_is_tracked(self):
        self.reservation.action_confirm()
        self.assertEqual(self.reservation.zee_deposit_paid, 0.0)
        self._register(400.0)
        self.assertEqual(self.reservation.zee_deposit_paid, 400.0)
        self.assertEqual(self.reservation.zee_balance_due, self.reservation.amount_total - 400.0)
        self.assertEqual(len(self.reservation.zee_payment_ids), 1)

    def test_deposits_cannot_exceed_the_total(self):
        self.reservation.action_confirm()
        with self.assertRaises(UserError):
            self._register(self.reservation.amount_total + 1)

    def test_deposit_cannot_be_higher_than_the_total_at_confirmation(self):
        self.reservation.zee_deposit_amount = self.reservation.amount_total + 1
        with self.assertRaises(UserError):
            self.reservation.action_confirm()

    def test_only_reservations_take_a_deposit(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [Command.create({'product_id': self.product.id})],
        })
        wizard = self.env['zee.reservation.deposit'].create({
            'order_id': order.id,
            'journal_id': self.journal.id,
            'amount': 10.0,
        })
        with self.assertRaises(UserError):
            wizard.action_register_deposit()

    def test_cancelled_reservation_releases_the_stock(self):
        self.env['stock.quant']._update_available_quantity(
            self.product, self.env.ref('stock.stock_location_stock'), 5.0,
        )
        self.reservation.action_confirm()
        picking = self.reservation.picking_ids
        picking.action_assign()
        self.assertEqual(picking.state, 'assigned')
        self.reservation._action_cancel()
        self.assertEqual(picking.state, 'cancel')
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.product.id),
            ('location_id', '=', self.env.ref('stock.stock_location_stock').id),
        ])
        self.assertEqual(quant.reserved_quantity, 0.0)
