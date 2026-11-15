from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .common import ZeeCommon


@tagged('post_install', '-at_install')
class TestReturnVoucher(ZeeCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('sales_team.group_sale_manager')
        cls.product = cls.env['product.product'].create({'name': "Returned item", 'list_price': 300.0})
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'invoice_line_ids': [Command.create({'product_id': cls.product.id, 'quantity': 1})],
        })
        cls.invoice.action_post()
        reversal = cls.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=cls.invoice.ids,
        ).create({'journal_id': cls.invoice.journal_id.id})
        cls.credit_note = cls.env['account.move'].browse(reversal.refund_moves()['res_id'])
        cls.credit_note.action_post()

    def test_issue_voucher_from_credit_note(self):
        self.credit_note.action_zee_issue_return_voucher()
        voucher = self.credit_note.zee_return_voucher_id
        self.assertEqual(voucher.partner_id, self.partner)
        self.assertEqual(voucher.points, 300.0)
        self.assertEqual(voucher.program_id.program_type, 'ewallet')

    def test_voucher_is_issued_once(self):
        self.credit_note.action_zee_issue_return_voucher()
        with self.assertRaises(UserError):
            self.credit_note.action_zee_issue_return_voucher()

    def test_only_credit_notes_get_vouchers(self):
        with self.assertRaises(UserError):
            self.invoice.action_zee_issue_return_voucher()

    def test_customer_is_required(self):
        order = self.env['pos.order'].new({'amount_total': -50.0, 'state': 'paid'})
        with self.assertRaises(UserError):
            order.action_zee_issue_return_voucher()

    def test_rights_are_checked(self):
        user = self.env['res.users'].create({
            'name': "Plain user",
            'login': 'zee_plain_user',
            'group_ids': [Command.set(self.env.ref('base.group_user').ids)],
        })
        with self.assertRaises(AccessError):
            self.env['loyalty.card'].with_user(user)._zee_issue_return_voucher(self.partner, 10.0)
