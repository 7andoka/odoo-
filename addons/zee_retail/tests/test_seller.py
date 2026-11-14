from datetime import datetime

from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged('post_install', '-at_install')
class TestSeller(BaseCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({'name': "Sold item", 'list_price': 1000.0})
        cls.seller_user = cls.env['res.users'].create({
            'name': "Seller user",
            'login': 'zee_seller_user',
            'group_ids': [Command.set(cls.env.ref('sales_team.group_sale_salesman').ids)],
        })
        cls.seller = cls.env['hr.employee'].create({
            'name': "Seller",
            'user_id': cls.seller_user.id,
            'zee_is_seller': True,
            'zee_seller_code': 'S1',
            'zee_monthly_target': 2000.0,
            'zee_commission_rate': 2.5,
        })

    def _confirmed_order(self, date_order):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'user_id': self.seller_user.id,
            'date_order': date_order,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        order.date_order = date_order
        return order

    def test_month_statistics(self):
        self._confirmed_order(datetime(2026, 3, 10, 12, 0))
        self._confirmed_order(datetime(2026, 3, 20, 12, 0))
        self._confirmed_order(datetime(2026, 4, 2, 12, 0))
        seller = self.seller.with_context(zee_stats_month='2026-03-15')
        self.assertEqual(seller.zee_month_sales, 2000.0)
        self.assertEqual(seller.zee_target_achievement, 100.0)
        self.assertEqual(seller.zee_remaining_target, 0.0)
        self.assertEqual(seller.zee_estimated_commission, 50.0)

    def test_remaining_target(self):
        self._confirmed_order(datetime(2026, 3, 10, 12, 0))
        seller = self.seller.with_context(zee_stats_month='2026-03-01')
        self.assertEqual(seller.zee_target_achievement, 50.0)
        self.assertEqual(seller.zee_remaining_target, 1000.0)

    def test_seller_code_is_unique(self):
        with self.assertRaises(Exception):  # noqa: B017 - ValidationError, kept loose on purpose
            self.env['hr.employee'].create({'name': "Twin", 'zee_is_seller': True, 'zee_seller_code': 'S1'})
