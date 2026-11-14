{
    'name': 'Zee Retail',
    'version': '1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Retail operations of the Zee-erp2 application on top of Odoo',
    'description': """
Zee Retail
==========

Adds to the standard Odoo applications the retail operations that were
running in the Zee-erp2 application and that Odoo does not cover natively.
""",
    'depends': [
        'account',
        'hr',
        'point_of_sale',
        'pos_hr',
        'pos_loyalty',
        'sale_loyalty',
        'sale_management',
        'stock',
    ],
    'data': [
        'security/ir.access.csv',
        'data/zee_retail_data.xml',
        'data/loyalty_data.xml',
        'data/zee_operations_data.xml',
        'views/product_category_views.xml',
        'views/product_attribute_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/hr_employee_views.xml',
        'views/pos_order_views.xml',
        'views/sale_order_views.xml',
        'wizard/zee_reservation_deposit_views.xml',
        'wizard/zee_seller_target_views.xml',
        'wizard/zee_reservation_settle_views.xml',
        'views/zee_reservation_views.xml',
        'views/zee_branch_transfer_views.xml',
        'views/zee_operations_views.xml',
        'views/zee_retail_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': True,
    'license': 'LGPL-3',
}
