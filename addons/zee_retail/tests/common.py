from odoo.addons.base.tests.common import BaseCommon


class ZeeCommon(BaseCommon):
    """Base for the Zee tests: the test user manages sales, stock, accounting, POS and HR."""

    _test_user_groups = (
        'base.group_user',
        'sales_team.group_sale_manager',
        'stock.group_stock_manager',
        'product.group_product_manager',
        'account.group_account_manager',
        'point_of_sale.group_pos_manager',
        'hr.group_hr_manager',
        'base.group_erp_manager',
    )
