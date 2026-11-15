from . import models
from . import wizard

# Payment methods used in Zee-erp2 that Odoo does not ship by default.
# Each one becomes a bank payment method with its own journal, per company.
ZEE_PAYMENT_METHODS = [
    ('InstaPay', 'ZIPAY'),
    ('Mobile Wallet', 'ZWLT'),
    ('Visa Card', 'ZVISA'),
]


def post_init_hook(env):
    """Create the Zee payment methods for every company, once, at install time."""
    PaymentMethod = env['pos.payment.method']
    for company in env['res.company'].search([]):
        company_env = env(context=dict(env.context, allowed_company_ids=company.ids))
        # The helper that picks the default outstanding account is not present in every
        # Odoo 20 build, so fall back to the company transfer account when it is missing.
        helper = getattr(PaymentMethod.with_env(company_env), '_get_default_outstanding_account', None)
        outstanding = helper(company) if helper else company.transfer_account_id
        for name, code in ZEE_PAYMENT_METHODS:
            if PaymentMethod.search_count([('name', '=', name), ('company_id', '=', company.id)]):
                continue
            journal = company_env['account.journal'].create({
                'name': name,
                'code': code,
                'type': 'bank',
                'company_id': company.id,
            })
            PaymentMethod.with_env(company_env).create({
                'name': name,
                'type': 'bank',
                'journal_id': journal.id,
                'outstanding_account_id': outstanding.id,
                'company_id': company.id,
            })
