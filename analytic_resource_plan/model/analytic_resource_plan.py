# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2014 Eficent (<http://www.eficent.com/>)
#              <contact@eficent.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.tools.translate import _
from openerp.osv import fields, orm
import openerp.addons.decimal_precision as dp
import time


class AnalyticResourcePlanLine(orm.Model):

    _name = 'analytic.resource.plan.line'
    _description = "Analytic Resource Planning lines"
    # _inherits = {'account.analytic.line.plan': "analytic_line_plan_id"}

    def _has_child(self, cr, uid, ids, field_names, arg, context=None):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id] = False
            if line.child_ids:
                res[line.id] = True
        return res

    def _subtotal(self, cr, uid, ids, field_names, arg, context=None):
        res = {}
        if not ids:
            return res
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id] = 0.0
            if line.unit_amount and line.price_unit:
                res[line.id] = line.unit_amount * line.price_unit
        return res

    _columns = {
        'supplier_id': fields.many2one(
            'res.partner',
            string='Supplier',
            required=False, readonly=True,
            domain=[('supplier', '=', True)],
            states={
                'draft': [('readonly', False)]
            },
        ),
        'pricelist_id': fields.many2one(
            'product.pricelist',
            string='Purchasing Pricelist',
            required=False, readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'price_unit': fields.float(
            string='Unit Price',
            required=False, readonly=True,
            digits_compute=dp.get_precision('Purchase Price'),
            states={
                'draft': [('readonly', False)]
            },
        ),
        'account_id': fields.many2one(
            'account.analytic.account',
            string='Analytic Account',
            ondelete='cascade', select=True,
            domain=[('type', '<>', 'view')],
            readonly=True, required=True,
            states={
                'draft': [('readonly', False)]
            }
        ),
        'name': fields.char(
            'Activity description', size=256,
            readonly=True, required=True,
            states={
                'draft': [('readonly', False)]
            }
        ),
        'date': fields.date(
            'Date', required=True, select=True, readonly=True,
            states={
                'draft': [('readonly', False)]
            }
        ),
        'state': fields.selection(
            [
                ('draft', 'Draft'), ('confirm', 'Confirmed')
            ],
            'Status',
            select=True, required=True, readonly=True,
            help=' * The \'Draft\' status is used when a user is encoding '
                 'a new and unconfirmed resource plan line. '
                 '\n* The \'Confirmed\' status is used for to confirm the '
                 'execution of the resource plan lines.'
        ),
        'product_id': fields.many2one(
            'product.product', string='Product',
            readonly=True, required=True,
            states={'draft': [('readonly', False)]}
        ),
        'product_uom_id': fields.many2one(
            'product.uom', string='UoM',
            required=True, readonly=True,
            states={
                'draft': [('readonly', False)]
            }
        ),
        'unit_amount': fields.float(
            string='Planned Quantity',
            required=True, readonly=True,
            states={
                'draft': [('readonly', False)]
            },
            help='Specifies the quantity that has '
            'been planned.'
        ),
        'notes': fields.text(string='Notes', readonly=True,),
        'parent_id': fields.many2one(
            'analytic.resource.plan.line',
            'Parent',
            readonly=True,
            ondelete='cascade'
        ),
        'child_ids': fields.one2many(
            'analytic.resource.plan.line',
            'parent_id',
            'Child lines', readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'has_child': fields.function(
            _has_child, type='boolean',
            string="Child lines", readonly=True,
        ),
        'analytic_line_plan_ids': fields.one2many(
            'account.analytic.line.plan',
            'resource_plan_id',
            string='Planned costs', readonly=True,
            states={
                'draft': [('readonly', False)]
            },
        ),
        'subtotal': fields.function(
            _subtotal, type='float',
            string='Subtotal', readonly=True,
            digits_compute=dp.get_precision('Purchase Price'),
            store={
                'analytic.resource.plan.line': (lambda self, cr, uid, ids, context=None: ids, ['unit_amount', 'unit_amount'], 10),
            },
        ),
    }

    _defaults = {
        'state': 'draft',
        'date': lambda *a: time.strftime('%Y-%m-%d'),
        'unit_amount': 1,
    }

    def copy(self, cr, uid, id, default=None, context=None):
        if context is None:
            context = {}
        if default is None:
            default = {}
        default['parent_id'] = False
        default['analytic_line_plan_ids'] = []
        res = super(AnalyticResourcePlanLine, self).copy(
            cr, uid, id, default, context)
        return res

    def _prepare_analytic_lines(self, cr, uid, line, context=None):
        plan_version_obj = self.pool.get('account.analytic.plan.version')
        res = {}
        res['value'] = {}
        journal_id = line.product_id.expense_analytic_plan_journal_id \
            and line.product_id.expense_analytic_plan_journal_id.id or False

        general_account_id = line.product_id.product_tmpl_id.\
            property_account_expense.id
        if not general_account_id:
            general_account_id = line.product_id.categ_id.\
                property_account_expense_categ.id
        if not general_account_id:
            raise orm.except_orm(_('Error !'),
                                 _('There is no expense account defined '
                                   'for this product: "%s" (id:%d)')
                                 % (line.product_id.name,
                                    line.product_id.id,))
        default_plan_ids = plan_version_obj.search(
            cr, uid, [('default_resource_plan', '=', True)],
            limit=1, context=context)

        if not default_plan_ids:
            raise orm.except_orm(_('Error !'),
                                 _('No active planning version for resource '
                                   'plan exists.'))

        return [{
            'resource_plan_id': line.id,
            'account_id': line.account_id.id,
            'name': line.name,
            'date': line.date,
            'product_id': line.product_id.id,
            'product_uom_id': line.product_uom_id.id,
            'unit_amount': line.unit_amount,
            'amount': -1 * line.price_unit * line.unit_amount,
            'general_account_id': general_account_id,
            'journal_id': journal_id,
            'notes': line.notes,
            'version_id': default_plan_ids[0],
            'currency_id': line.account_id.company_id.currency_id.id,
            'amount_currency': line.price_unit,
        }]

    def create_analytic_lines(self, cr, uid, line, context=None):
        res = []
        line_plan_obj = self.pool.get('account.analytic.line.plan')
        lines_vals = self._prepare_analytic_lines(
            cr, uid, line, context=context
        )
        for line_vals in lines_vals:
            line_id = line_plan_obj.create(cr, uid, line_vals, context=context)
            res.append(line_id)
        return res

    def _delete_analytic_lines(self, cr, uid, line, context=None):
        line_plan_obj = self.pool.get('account.analytic.line.plan')
        ana_line_ids = line_plan_obj.search(
            cr, uid,
            [('resource_plan_id', '=', line.id)],
            context=context)
        line_plan_obj.unlink(cr, uid, ana_line_ids, context=context)
        return True

    def action_button_draft(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context=context):
            for child in line.child_ids:
                if child.state not in ('draft', 'plan'):
                    raise orm.except_orm(
                        _('Error'),
                        _('All the child resource plan lines must be in '
                          'Draft state.')
                    )
            self._delete_analytic_lines(cr, uid, line, context=context)
        return self.write(cr, uid, ids, {'state': 'draft'}, context=context)

    def action_button_confirm(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context=context):
            if line.unit_amount == 0:
                raise orm.except_orm(
                    _('Error'),
                    _('Quantity should be greater than 0.')
                )
            if not line.child_ids:
                self.create_analytic_lines(cr, uid, line, context=context)
        return self.write(cr, uid, ids, {'state': 'confirm'}, context=context)

    def on_change_product_id(self, cr, uid, id, product_id, context=None):
        res = dict()
        res['value'] = {}
        if product_id:
            prod = self.pool.get('product.product').browse(
                cr, uid, product_id, context=context
            )
            res['value'].update({'name': prod.name})
            prod_uom = prod.uom_id and prod.uom_id.id or False
            res['value'].update({'product_uom_id': prod_uom})
            prod_price = prod.standard_price or 0.0
            res['value'].update({'price_unit': prod_price})
        return res

    def on_change_account_id(self, cr, uid, id, account_id, context=None):
        res = dict()
        res['value'] = {}
        if account_id:
            account = self.pool.get('account.analytic.account').browse(
                cr, uid, account_id, context=context
            )
            if account.date:
                res['value'].update({'date': account.date})
        return res

    def create(self, cr, uid, vals, context=None):
        if 'project' in vals:
            pp = self.pool.get('project.project')
            pp_obj = pp.browse(cr, uid, vals['project'])
            vals['account_id'] = pp_obj.analytic_account_id.id
        return super(AnalyticResourcePlanLine, self).create(cr, uid, vals, context=context)

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if isinstance(ids, (int, long)):
            ids = [ids]
        analytic_obj = self.pool.get('account.analytic.account')

        if 'account_id' in vals:
            analytic = analytic_obj.browse(
                cr, uid, vals['account_id']
            )
            if not vals.get('date', False):
                vals['date'] = analytic.date

        return super(AnalyticResourcePlanLine, self).write(
            cr, uid, ids, vals, context=context
        )

    def unlink(self, cr, uid, ids, context=None):
        for line in self.browse(cr, uid, ids, context=context):
            if line.analytic_line_plan_ids:
                raise orm.except_orm(
                    _('Error!'),
                    _('You cannot delete a record that refers to analytic '
                      'plan lines!'))
        return super(AnalyticResourcePlanLine, self).unlink(
            cr, uid, ids, context=context
        )
