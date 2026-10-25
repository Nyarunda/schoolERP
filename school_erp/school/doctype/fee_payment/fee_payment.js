// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("Fee Payment", {
	setup(frm) {
		frm.set_query("student", () => ({ filters: { status: ["!=", "Graduated"] } }));
		// Only this student's unpaid invoices, and only the fee types still owed on the chosen invoice
		frm.set_query("sales_invoice", "allocations", () => ({
			filters: { student: frm.doc.student || "", docstatus: 1, is_return: 0, outstanding_amount: [">", 0] },
		}));
		frm.set_query("fee_type", "allocations", (doc, cdt, cdn) => {
			const inv = locals[cdt][cdn].sales_invoice;
			return inv ? { filters: { name: ["in", open_lines_for(frm, inv).map((l) => l.fee_type)] } } : {};
		});
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.mode_of_payment) {
			frappe.db.get_single_value("School Settings", "default_mode_of_payment").then((m) => m && frm.set_value("mode_of_payment", m));
		}
	},

	refresh(frm) {
		frm.set_df_property("allocations", "read_only", frm.doc.manual_allocation ? 0 : 1);
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Print Receipt"), () => frm.print_doc());
			if (frm.doc.payment_entry) {
				frm.add_custom_button(__("Payment Entry"), () => frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry), __("View"));
			}
			frm.add_custom_button(__("Student"), () => frappe.set_route("Form", "Student", frm.doc.student), __("View"));
		}
		show_balances(frm);
	},

	student(frm) {
		if ((frm.doc.allocations || []).length) frm.clear_table("allocations");
		frm.refresh_field("allocations");
		show_balances(frm);
		if (frm.doc.student) {
			frappe.db.get_value("Student", frm.doc.student, ["primary_guardian", "primary_phone"]).then(({ message }) => {
				if (!frm.doc.payer_name) frm.set_value("payer_name", message.primary_guardian);
				if (!frm.doc.payer_phone) frm.set_value("payer_phone", message.primary_phone);
			});
		}
	},

	manual_allocation(frm) {
		frm.set_df_property("allocations", "read_only", frm.doc.manual_allocation ? 0 : 1);
	},
});

frappe.ui.form.on("Fee Payment Allocation", {
	sales_invoice(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const lines = open_lines_for(frm, row.sales_invoice);
		frappe.model.set_value(cdt, cdn, "school_term", lines.length ? lines[0].school_term : null);
		frappe.model.set_value(cdt, cdn, "fee_type", lines.length === 1 ? lines[0].fee_type : null);
	},

	fee_type(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const line = open_lines_for(frm, row.sales_invoice).find((l) => l.fee_type === row.fee_type);
		frappe.model.set_value(cdt, cdn, "outstanding", line ? line.outstanding : 0);
		if (line && !row.allocated_amount) frappe.model.set_value(cdt, cdn, "allocated_amount", line.outstanding);
	},
});

function open_lines_for(frm, invoice) {
	return (frm.open_lines || []).filter((l) => l.sales_invoice === invoice);
}

const BALANCE_CARD_CSS = `
	.fp-bal { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg, 12px); padding: 14px 16px; background: var(--card-bg, var(--fg-color)); }
	.fp-bal.owed { border-color: var(--orange-200, #fed7aa); background: var(--orange-50, #fff7ed); }
	.fp-bal.clear { border-color: var(--green-200, #bbf7d0); background: var(--green-50, #f0fdf4); }
	.fp-bal-lbl { font-size: var(--text-xs); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; color: var(--text-muted); }
	.fp-bal.owed .fp-bal-lbl { color: var(--orange-700, #c2410c); } .fp-bal.clear .fp-bal-lbl { color: var(--green-700, #15803d); }
	.fp-bal-amt { font-size: 24px; font-weight: 700; color: var(--text-color); margin: 2px 0 10px; font-variant-numeric: tabular-nums; }
	.fp-bal-rows { display: flex; flex-direction: column; gap: 4px; }
	.fp-bal-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; width: 100%; padding: 6px 10px; border-radius: 8px;
		border: 1px solid transparent; background: var(--fg-color); font-size: var(--text-sm); color: var(--text-color); cursor: pointer; text-align: left; }
	.fp-bal-row:hover, .fp-bal-row.on { border-color: var(--primary); }
	.fp-bal-row span:last-child { font-weight: 600; font-variant-numeric: tabular-nums; }
	.fp-bal-foot { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
	.fp-bal-foot small { color: var(--text-muted); }
	.fp-bal-empty { color: var(--text-muted); font-size: var(--text-sm); padding: 18px 4px; text-align: center; }
`;

function show_balances(frm) {
	const field = frm.get_field("balance_html");
	if (!field) return;
	if (!document.getElementById("fp-bal-css")) {
		$(`<style id="fp-bal-css">${BALANCE_CARD_CSS}</style>`).appendTo("head");
	}
	const $w = $(field.wrapper).empty();

	if (frm.doc.docstatus !== 0) {
		if (frm.doc.balance_before == null && frm.doc.balance_after == null) return;
		const after = frm.doc.balance_after || 0;
		$w.html(`<div class="fp-bal ${after > 0 ? "owed" : "clear"}">
			<div class="fp-bal-lbl">${after < 0 ? __("Credit after this payment") : __("Balance after this payment")}</div>
			<div class="fp-bal-amt">${format_currency(Math.abs(after))}</div>
			<div class="fp-bal-foot"><small>${__("Before")}: ${format_currency(frm.doc.balance_before || 0)}</small></div></div>`);
		return;
	}
	if (!frm.doc.student) {
		$w.html(`<div class="fp-bal fp-bal-empty">${__("Select a student to see what they owe")}</div>`);
		return;
	}
	const student = frm.doc.student;
	frappe.call("school_erp.api.payments.get_open_balances", { student }).then(({ message: m }) => {
		if (!m || frm.doc.student !== student) return;
		frm.open_lines = m.lines;
		if (!m.by_fee_type.length) {
			$w.html(`<div class="fp-bal clear"><div class="fp-bal-lbl">${__("Nothing owed")}</div>
				<div class="fp-bal-amt">${format_currency(Math.max(-m.balance, 0))}</div>
				<small class="text-muted">${m.balance < 0 ? __("Credit on account. ") : ""}${__("This payment will be kept as an advance.")}</small></div>`);
			return;
		}
		const rows = m.by_fee_type.map((r) => `<button type="button" class="fp-bal-row" data-fee-type="${frappe.utils.escape_html(r.fee_type)}" data-amount="${r.outstanding}"
			title="${__("Pay only this")}"><span>${frappe.utils.escape_html(r.fee_type)}</span><span>${format_currency(r.outstanding)}</span></button>`).join("");
		$w.html(`<div class="fp-bal ${m.balance > 0 ? "owed" : "clear"}">
			<div class="fp-bal-lbl">${__("Currently owed")}</div>
			<div class="fp-bal-amt">${format_currency(m.balance)}</div>
			<div class="fp-bal-rows">${rows}</div>
			<div class="fp-bal-foot"><small>${__("Tap a fee to pay only that")}</small>
				<button type="button" class="btn btn-xs btn-primary fp-pay-all">${__("Pay full balance")}</button></div></div>`);

		$w.find(".fp-pay-all").on("click", async () => {
			await frm.set_value("allocation_method", "Oldest balance first");
			await frm.set_value("target_fee_types", []);
			await frm.set_value("amount", flt(m.balance, 2));
		});
		$w.find(".fp-bal-row").on("click", async (e) => {
			const d = e.currentTarget.dataset;
			await frm.set_value("allocation_method", "Specific fee types");
			await frm.set_value("target_fee_types", [{ fee_type: d.feeType }]);
			await frm.set_value("amount", flt(d.amount, 2));
			$w.find(".fp-bal-row").removeClass("on");
			$(e.currentTarget).addClass("on");
		});
	});
}
