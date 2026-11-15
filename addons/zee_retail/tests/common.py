from odoo.addons.base.tests.common import BaseCommon


class ZeeCommon(BaseCommon):
    """Base for the Zee tests: the test user manages sales, stock, accounting, POS and HR."""

    @classmethod
    def get_default_groups(cls):
        groups = super().get_default_groups()
        for xmlid in (
            'sales_team.group_sale_manager',
            'stock.group_stock_manager',
            'account.group_account_manager',
            'point_of_sale.group_pos_manager',
            'hr.group_hr_manager',
            'base.group_erp_manager',
        ):
            groups |= cls.env.ref(xmlid)
        return groups
