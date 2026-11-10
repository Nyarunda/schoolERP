// Copyright (c) 2026, School ERP and contributors

frappe.ui.form.on("School Settings", {
	setup(frm) {
		frm.set_query("default_income_account", () => ({ filters: { company: frm.doc.company, root_type: "Income", is_group: 0 } }));
		frm.set_query("cost_center", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},

	refresh(frm) {
		frm.add_custom_button(__("Run School Setup"), () => {
			frappe.confirm(__("Create classes, fee types, terms, periods and subjects that are missing? Nothing existing is changed."), () => {
				frappe.call({ method: "school_erp.api.setup.run_setup", freeze: true, freeze_message: __("Setting up...") }).then(({ message }) => {
					frappe.msgprint({
						title: __("Setup complete"),
						indicator: "green",
						message: `<p>${__("Created")}: ${message.created.join(", ") || __("nothing new")}</p>
							<p><b>${__("Next steps")}</b></p><ol>${message.next_steps.map((s) => `<li>${s}</li>`).join("")}</ol>`,
					});
					frm.reload_doc();
				});
			});
		});
		render_license(frm);
		render_tax_status(frm);
		setup_mpesa(frm);
		if (((frappe.boot.school_erp || {}).modules || []).includes("portal")) {
			frm.add_custom_button(__("Give All Parents Portal Access"), () =>
				frappe.confirm(__("Create parent portal logins for the guardians of every active student and SMS them their password?"), () =>
					frappe.call({ method: "school_erp.api.portal.give_portal_access", args: { all_students: 1 }, freeze: true, freeze_message: __("Creating logins...") })
						.then(({ message: m }) => frappe.msgprint(__("{0} new parent logins created, {1} guardians linked, {2} without a phone or email.", [m.new_logins, m.linked, m.without_contact])))),
				__("Parent Portal"));
		}
	},
	mpesa_callback_base_url: render_mpesa_urls,
	mpesa_enabled: render_mpesa_urls,
});

function setup_mpesa(frm) {
	render_mpesa_urls(frm);
	if (!frm.doc.mpesa_enabled) return;
	const grp = __("M-Pesa");
	const till = (frm.doc.mpesa_account_type || "").startsWith("Till");
	// a Till payment has no account number; the payer's phone is what can match it to a student
	const test_fields = (amount_type, amount) => till
		? [
			{ fieldname: "msisdn", label: __("Payer phone (as M-Pesa reports it)"), fieldtype: "Data", default: "254712345678",
			  description: __("Matches a student when exactly one active student has a guardian with this number") },
			{ fieldname: "amount", label: __("Amount"), fieldtype: amount_type, reqd: 1, default: amount },
		]
		: [
			{ fieldname: "bill_ref_number", label: __("Account No. (Student ID)"), fieldtype: "Data", reqd: 1 },
			{ fieldname: "amount", label: __("Amount"), fieldtype: amount_type, reqd: 1, default: amount },
		];

	frm.add_custom_button(__("Register URLs with Safaricom"), () => {
		if (frm.is_dirty()) return frappe.msgprint(__("Save first"));
		frappe.confirm(__("Register this site's callback URLs for {0} {1} ({2})?", [till ? __("store") : __("paybill"), frm.doc.mpesa_shortcode, frm.doc.mpesa_environment]), () =>
			frappe.call({ method: "school_erp.api.paybill.register_urls", freeze: true, freeze_message: __("Contacting Safaricom...") })
				.then(({ message }) => {
					frappe.msgprint({ title: __("Registered"), indicator: "green", message: `<pre>${frappe.utils.escape_html(JSON.stringify(message.response, null, 1))}</pre>` });
					frm.reload_doc();
				}));
	}, grp);

	frm.add_custom_button(__("Test Payment (offline)"), () => {
		frappe.prompt(
			[...test_fields("Currency", 1000), { fieldname: "payer", label: __("Payer name"), fieldtype: "Data", default: "Test Parent" }],
			(v) => frappe.call({ method: "school_erp.api.paybill.local_test_payment", args: v, freeze: true }).then(({ message: m }) => {
				frappe.msgprint({
					title: __("Test payment {0}", [m.name]),
					indicator: m.status === "Posted" ? "green" : "orange",
					message: `${__("Status")}: <b>${m.status}</b>${m.student ? `<br>${__("Student")}: ${m.student}` : ""}${m.fee_payment ? `<br>${__("Fee Payment")}: <a href="${frappe.utils.get_form_link("Fee Payment", m.fee_payment)}">${m.fee_payment}</a>` : ""}${m.error ? `<br>${frappe.utils.escape_html(m.error)}` : ""}`,
				});
			}),
			till ? __("Simulate a parent paying the Till (no Safaricom involved)") : __("Simulate a parent paying the Paybill (no Safaricom involved)"),
			__("Pay"),
		);
	}, grp);

	if (frm.doc.mpesa_environment === "Sandbox") {
		frm.add_custom_button(__("Simulate via Safaricom Sandbox"), () => {
			frappe.prompt(
				test_fields("Int", 100),
				(v) => frappe.call({ method: "school_erp.api.paybill.simulate", args: v, freeze: true }).then(({ message }) =>
					frappe.msgprint(`<pre>${frappe.utils.escape_html(JSON.stringify(message, null, 1))}</pre>` +
						__("If accepted, Safaricom calls your confirmation URL within a few seconds. Check M-Pesa Transaction."))),
				__("Sandbox payment"),
			);
		}, grp);
	}

	frm.add_custom_button(__("M-Pesa Transactions"), () => frappe.set_route("List", "M-Pesa Transaction"), grp);
}

function render_mpesa_urls(frm) {
	const f = frm.get_field("mpesa_urls_html");
	if (!f) return;
	if (!frm.doc.mpesa_enabled || !frm.doc.mpesa_callback_token) {
		f.$wrapper.html(`<div class="text-muted small">${__("Tick 'Auto-post M-Pesa payments' and save to generate the callback URLs.")}</div>`);
		return;
	}
	const base = (frm.doc.mpesa_callback_base_url || window.location.origin).replace(/\/$/, "");
	const q = `?token=${frm.doc.mpesa_callback_token}`;
	const warn = /mpesa|m-pesa|safaricom|localhost|127\.0\.0\.1/i.test(base) || !base.startsWith("https://");
	f.$wrapper.html(`
		<div class="small">
			<div><b>${__("Confirmation URL")}</b><br><code>${base}/api/method/school_erp.api.paybill.confirm${q}</code></div>
			<div style="margin-top:6px"><b>${__("Validation URL")}</b><br><code>${base}/api/method/school_erp.api.paybill.validate${q}</code></div>
			${warn ? `<div style="margin-top:8px;color:var(--orange-600)">${__("Safaricom needs a public https address without the words mpesa/safaricom. Set 'Public Site URL'.")}</div>` : ""}
			<div class="text-muted" style="margin-top:6px">${__("Keep these URLs private: the token in them is what proves a callback is genuine.")}</div>
		</div>`);
}

// What each module adds, in the school's words (codes from school_erp.logic.license.MODULES)
const MODULE_HELP = {
	fees: __("Fee structures, termly billing, receipts and fee statements"),
	timetable: __("Class timetables, subjects, periods and double lessons"),
	transport: __("Bus routes and transport fees"),
	lunch: __("Lunch programme fees"),
	activities: __("Games, clubs and activity fees"),
	messaging: __("Bulk SMS and email to parents: fee reminders, results, notices"),
	mpesa: __("Paybill and Till payments posted to the student automatically"),
	staff: __("Staff records, leave, duty rosters and duty reports"),
	welfare: __("Discipline incidents and complaints"),
	expenses: __("School expenses with approval steps"),
	transport_ops: __("Vehicles, fuel and drivers' daily logs"),
	exams: __("Exams, mark sheets, merit lists and report cards"),
	portal: __("Parent portal: balances, report cards and M-Pesa prompts to pay"),
	health: __("Learner health records, sick bay visits with parent SMS, visitor book and gate passes"),
	library: __("Book catalogue with copies, issue and return, renewals, overdue SMS and fines billed to fees"),
	pocket_money: __("Learners' pocket money: deposits, canteen purchases, daily limits, balance on the parent portal"),
	boarding: __("Dormitories, bed allocation, exeat passes with gate check-out/in and parent SMS"),
	homework: __("Homework per stream and subject, hand-in tracking, on the parent portal"),
	admissions: __("Online application form, interviews, offers and one-click admission"),
};

function render_license(frm) {
	const $w = frm.get_field("license_status_html").$wrapper;
	frappe.call("school_erp.licensing.license_overview").then(({ message: s }) => {
		$w.html(license_panel(frm, s));
		$w.find(".sl-copy").on("click", (e) => frappe.utils.copy_to_clipboard($(e.currentTarget).data("copy")));
		$w.find(".sl-install").on("click", () => install_key(frm));
	});
}

// The key on its own: works before the rest of School Settings (school name, company) has been filled in
function install_key(frm) {
	frappe.prompt({ fieldname: "key", fieldtype: "Small Text", label: __("License key from your vendor"), reqd: 1 }, ({ key }) =>
		frappe.call({ method: "school_erp.licensing.install_key", args: { key }, freeze: true }).then(() => {
			frappe.show_alert({ message: __("License key installed"), indicator: "green" });
			frm.reload_doc();
		}), __("Install license key"), __("Install"));
}

function license_panel(frm, s) {
	const esc = frappe.utils.escape_html;
	const fmt = (d) => (d ? frappe.datetime.str_to_user(d) : "");
	const days = s.days_left;
	const soon = s.status === "valid" && days !== null && days <= 30;
	const look = {
		valid: soon ? ["orange", "triangle-alert", __("Renewal due soon")] : ["green", "check", __("License active")],
		grace: ["orange", "triangle-alert", __("Expired: grace period")],
		expired: ["red", "lock", __("License expired")],
		invalid: ["red", "x", __("Key not accepted")],
		unlicensed: ["gray", "lock", __("No license yet")],
	}[s.status] || ["gray", "lock", s.status];
	const [color, icon, title] = look;
	const grace_end = s.expires ? frappe.datetime.add_days(s.expires, 14) : null;

	// What it means for the school, and what to do next
	const next = {
		valid: soon
			? __("Everything works as normal. Ask your vendor for a renewal key before {0} and paste it below; nothing has to be re-entered.", [fmt(s.expires)])
			: s.expires
				? __("Everything included below is switched on. You will be reminded 30 days before it ends on {0}.", [fmt(s.expires)])
				: __("Everything included below is switched on, with no end date."),
		grace: __("Everything still works for now. From {0} records become read-only until a renewal key is added. Fee payments and M-Pesa can always be received.", [fmt(grace_end)]),
		expired: __("Records can be viewed but not added or changed. Fee payments and M-Pesa are still received, so no money is lost. Paste a renewal key below to unlock everything again."),
		invalid: s.site && s.site !== s.this_site
			? __("This key was made for {0}, but this site is {1}. Ask your vendor for a key for this site.", [esc(s.site), esc(s.this_site)])
			: __("{0} Check that you pasted the whole key exactly as sent. The school is running on the free core until a valid key is saved.", [esc(s.message)]),
		unlicensed: __("Only Students, Classes, Streams, Teachers, Years and Terms are available. Send your vendor the site name below to get a key."),
	}[s.status] || esc(s.message);

	// Term progress: how much of the paid period is used
	let term = "";
	if (s.expires && s.issued && ["valid", "grace"].includes(s.status)) {
		const total = Math.max(frappe.datetime.get_diff(s.expires, s.issued), 1);
		const used = Math.min(Math.max(frappe.datetime.get_diff(frappe.datetime.get_today(), s.issued), 0), total);
		const left = s.status === "grace" ? __("{0} days left to renew", [14 + days]) : __("{0} days left", [days]);
		term = `<div class="sl-meter"><div class="sl-meter-head"><span>${__("Subscription period")}</span><b>${left}</b></div>
			<div class="sl-bar"><span class="${color}" style="width:${s.status === "grace" ? 100 : Math.round((used / total) * 100)}%"></span></div>
			<div class="sl-meter-foot"><span>${fmt(s.issued)}</span><span>${fmt(s.expires)}</span></div></div>`;
	}

	// Student limit
	const max = s.max_students || 0;
	const pct = max ? Math.min(Math.round((s.active_students / max) * 100), 100) : 0;
	const scolor = !max ? "green" : pct >= 100 ? "red" : pct >= 90 ? "orange" : "green";
	const students = `<div class="sl-meter"><div class="sl-meter-head"><span>${__("Active students")}</span>
		<b>${max ? __("{0} of {1}", [s.active_students, max]) : __("{0} (no limit)", [s.active_students])}</b></div>
		${max ? `<div class="sl-bar"><span class="${scolor}" style="width:${pct}%"></span></div>
		<div class="sl-meter-foot"><span>${pct >= 100 ? __("Limit reached: new students cannot be admitted") : __("{0} places left", [max - s.active_students])}</span></div>` : ""}</div>`;

	const facts = [
		[__("Licensed to"), s.licensed_to],
		[__("Valid for site"), s.site || (s.licensed_to ? __("Any site") : "")],
		[__("Issued"), fmt(s.issued)],
		[__("Expires"), s.expires ? fmt(s.expires) : s.licensed_to ? __("Never") : ""],
	].filter(([, v]) => v).map(([k, v]) => `<div><span>${k}</span><b>${esc(v)}</b></div>`).join("");

	// Only what the license includes is listed: the rest of the app is hidden from this school, so it is not shown here either
	const included = s.catalogue.filter((m) => m.included).length, more = s.catalogue.length - included;
	const modules = s.catalogue.filter((m) => m.included).map((m) => `
		<div class="sl-mod on">
			<span class="sl-mod-icon">${frappe.utils.icon("check", "sm")}</span>
			<div><b>${esc(__(m.label))}</b><small>${esc(MODULE_HELP[m.code] || "")}</small></div>
		</div>`).join("");

	return `<style>
		.sl{display:grid;gap:16px;margin-bottom:8px}
		.sl-hero{display:flex;gap:14px;padding:16px 18px;border-radius:10px;border:1px solid var(--border-color);border-left:4px solid var(--sl-c);background:var(--sl-bg)}
		.sl-hero.green{--sl-c:var(--green-500);--sl-bg:var(--green-highlight-color, var(--bg-green))}
		.sl-hero.orange{--sl-c:var(--orange-500);--sl-bg:var(--bg-orange)}
		.sl-hero.red{--sl-c:var(--red-500);--sl-bg:var(--bg-red)}
		.sl-hero.gray{--sl-c:var(--gray-500);--sl-bg:var(--subtle-fg)}
		.sl-hero-icon{flex:none;width:40px;height:40px;border-radius:50%;display:grid;place-items:center;background:var(--sl-c);color:#fff}
		.sl-hero-icon svg{stroke:#fff}
		.sl-hero h4{margin:0 0 4px;font-size:var(--text-lg);font-weight:600}
		.sl-hero p{margin:0;color:var(--text-color);line-height:1.5}
		.sl-facts{display:flex;flex-wrap:wrap;gap:6px 28px;margin-top:10px}
		.sl-facts div{display:flex;flex-direction:column}
		.sl-facts span,.sl-meter-head span,.sl-meter-foot{color:var(--text-muted);font-size:var(--text-xs)}
		.sl-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
		.sl-meter{padding:12px 14px;border:1px solid var(--border-color);border-radius:10px}
		.sl-meter-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
		.sl-bar{height:8px;border-radius:99px;background:var(--control-bg);overflow:hidden}
		.sl-bar span{display:block;height:100%;border-radius:99px}
		.sl-bar .green{background:var(--green-500)}.sl-bar .orange{background:var(--orange-500)}.sl-bar .red{background:var(--red-500)}
		.sl-meter-foot{display:flex;justify-content:space-between;margin-top:6px}
		.sl-h{display:flex;justify-content:space-between;align-items:baseline;margin:4px 0 -4px}
		.sl-h b{font-size:var(--text-md)}.sl-h span{color:var(--text-muted);font-size:var(--text-sm)}
		.sl-mods{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px}
		.sl-mod{display:flex;gap:10px;padding:10px 12px;border:1px solid var(--border-color);border-radius:8px}
		.sl-mod b{display:block;font-size:var(--text-sm)}.sl-mod small{color:var(--text-muted);line-height:1.4}
		.sl-mod-icon{flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center}
		.sl-mod.on .sl-mod-icon{background:var(--green-500)}.sl-mod.on .sl-mod-icon svg{stroke:#fff}
		.sl-mod.off{background:var(--subtle-fg);border-style:dashed}.sl-mod.off b{color:var(--text-muted)}
		.sl-mod.off .sl-mod-icon{background:var(--control-bg)}
		.sl-site{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px 14px;border-radius:10px;background:var(--subtle-fg);font-size:var(--text-sm)}
		.sl-site code{font-size:var(--text-sm)}
	</style>
	<div class="sl">
		<div class="sl-hero ${color}">
			<div class="sl-hero-icon">${frappe.utils.icon(icon, "md")}</div>
			<div><h4>${title}</h4><p>${next}</p>${facts ? `<div class="sl-facts">${facts}</div>` : ""}</div>
		</div>
		<div class="sl-row">${term}${students}</div>
		<div class="sl-h"><b>${__("What's included")}</b><span>${included ? __("Core and {0} module(s)", [included]) : __("Core only")}</span></div>
		<div class="sl-mods">
			<div class="sl-mod on"><span class="sl-mod-icon">${frappe.utils.icon("check", "sm")}</span>
				<div><b>${__("Core")}</b><small>${__("Students, classes, streams, teachers, years and terms. Always included.")}</small></div></div>
			${modules}
		</div>
		${more ? `<div class="text-muted small">${__("{0} more module(s) can be added to this license by your vendor; they stay hidden until then.", [more])}</div>` : ""}
		<div class="sl-site">${__("This site")}: <code>${esc(s.this_site)}</code>
			<button class="btn btn-xs btn-default sl-copy" data-copy="${esc(s.this_site)}">${__("Copy")}</button>
			<button class="btn btn-xs btn-primary sl-install">${s.status === "unlicensed" ? __("Install Key") : __("Install New Key")}</button>
			<span class="text-muted">${__("Your vendor needs this name to make a key for this school.")}</span></div>
	</div>`;
}

// What the school's tax settings mean, in one place on the Tax tab
function render_tax_status(frm) {
	const d = frm.doc;
	const on = (ok, text) => `<li style="margin:3px 0">${ok ? "✓" : "–"} ${text}</li>`;
	frm.get_field("tax_status_html").$wrapper.html(`<div class="small" style="margin-bottom:8px">
		<ul style="list-style:none;padding:0;margin:0">
			${on(d.vat_registered, d.vat_registered
				? __("VAT-registered: fee invoices carry {0}% VAT on Standard Rated fee types (set on each Fee Type); fee amounts already include it.", [d.vat_rate || 16])
				: __("Not VAT-registered: invoices carry no VAT, and VAT a supplier charges is part of the cost."))}
			${on(d.vat_registered, d.vat_registered ? __("VAT a supplier charges is claimable as input VAT.") : __("No input VAT to claim."))}
			${on(d.withhold_tax, d.withhold_tax ? __("Withholding tax is deducted from supplier payments by type (Withholding Tax Type).") : __("No withholding tax is deducted from supplier payments."))}
			${on(d.vat_withholding_agent, d.vat_withholding_agent ? __("As a VAT withholding agent, {0}% VAT is withheld from suppliers who charge VAT.", [d.vat_wht_rate || 2]) : __("Not a VAT withholding agent."))}
		</ul>
		<div class="text-muted" style="margin-top:6px">${__("Monthly figures: reports VAT Summary and Withholding Tax Register. Rates follow what you set here; confirm them with KRA or your tax adviser.")}</div>
	</div>`);
}
