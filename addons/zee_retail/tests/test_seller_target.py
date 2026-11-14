from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.zee_retail.tools.seller_target import active_days_ratio, distribute_target


@tagged('post_install', '-at_install')
class TestSellerTarget(TransactionCase):

    def test_active_days_ratio(self):
        self.assertEqual(active_days_ratio(None, 2026, 3), (31, 31, 1.0))
        self.assertEqual(active_days_ratio(date(2026, 1, 20), 2026, 3), (31, 31, 1.0))
        self.assertEqual(active_days_ratio(date(2026, 4, 1), 2026, 3), (31, 0, 0.0))
        self.assertEqual(active_days_ratio(date(2026, 3, 1), 2026, 3), (31, 31, 1.0))
        total, active, ratio = active_days_ratio(date(2026, 3, 16), 2026, 3)
        self.assertEqual((total, active), (31, 16))
        self.assertAlmostEqual(ratio, 16 / 31)

    def test_distribution_adds_up(self):
        shares = distribute_target(1000, [(1, 1.0), (2, 1.0), (3, 1.0)], 'equal')
        self.assertEqual(round(sum(shares.values()), 2), 1000.0)
        shares = distribute_target(1000, [(1, 1.0), (2, 0.5)], 'prorated')
        self.assertEqual(shares, {1: 666.67, 2: 333.33})

    def test_wizard_writes_the_shares(self):
        sellers = self.env['hr.employee'].create([
            {'name': "Seller A", 'zee_is_seller': True},
            {'name': "Seller B", 'zee_is_seller': True, 'zee_join_date': date(2026, 3, 16)},
        ])
        wizard = self.env['zee.seller.target'].create({
            'month': date(2026, 3, 1),
            'total_target': 3100.0,
            'method': 'prorated',
            'seller_ids': [(6, 0, sellers.ids)],
        })
        wizard.action_distribute()
        self.assertEqual(sum(sellers.mapped('zee_monthly_target')), 3100.0)
        self.assertGreater(sellers[0].zee_monthly_target, sellers[1].zee_monthly_target)

    def test_wizard_needs_sellers(self):
        wizard = self.env['zee.seller.target'].create({'total_target': 100.0, 'seller_ids': [(6, 0, [])]})
        with self.assertRaises(UserError):
            wizard.action_distribute()
