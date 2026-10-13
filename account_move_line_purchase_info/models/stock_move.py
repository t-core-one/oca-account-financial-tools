# Copyright 2019 ForgeFlow S.L.
#   (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = "stock.move"

    def _prepare_account_move_line(
        self, qty, cost, credit_account_id, debit_account_id, svl_id, description
    ):
        res = super(StockMove, self)._prepare_account_move_line(
            qty, cost, credit_account_id, debit_account_id, svl_id, description
        )
        for line in res:
            line[2]["purchase_line_id"] = self.purchase_line_id.id
        return res

    def _get_currency_convert_date(self):
        """Look at vendor bills only when picking the FX conversion date.

        `purchase.order.line.invoice_lines` is a plain one2many over every
        `account.move.line` carrying a `purchase_line_id`, and core assumes only
        vendor bills ever do.  `_prepare_account_move_line` above breaks that
        assumption: it stamps the PO line on every stock valuation line too, so
        Inventory Valuation entries end up in the set core believes to be bills.

        Those entries are `move_type='entry'` and have no `invoice_date`, so
        core's

            max(posted_bills.mapped("invoice_date"), default=convert_date)

        compares a `date` against `False` and dies with "'>' not supported
        between instances of 'datetime.date' and 'bool'".  `default=` only
        covers an *empty* list, never a falsy member of a non-empty one.

        Restricting the set to dated purchase documents is what core meant by
        "posted_bills"; the rest of the method mirrors it.  Seen on metacom-bg
        (PO line of P00536, billed 5100 against 0 received) and latent on
        t-blok.
        """
        self.ensure_one()
        # The date must be today, and not the date of the move since the move is
        # still in assigned state. See core purchase_stock/models/stock_move.py.
        convert_date = (
            fields.Date.context_today(self) if self.state != "done" else self.date
        )
        line = self.purchase_line_id
        if not line:
            return convert_date

        # Use currency rate at bill date when invoice before receipt
        qty_received = self._get_qty_received_without_self()
        if (
            float_compare(
                line.qty_invoiced,
                qty_received,
                precision_rounding=line.product_uom.rounding,
            )
            > 0
        ):
            posted_bills = line.sudo().invoice_lines.move_id.filtered(
                lambda m: m.state == "posted"
                and m.is_purchase_document(include_receipts=True)
                and m.invoice_date
            )
            convert_date = max(
                posted_bills.mapped("invoice_date"), default=convert_date
            )
        return convert_date
