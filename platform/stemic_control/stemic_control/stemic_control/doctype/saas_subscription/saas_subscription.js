const SUB_COLORS = { Trial: "blue", Active: "green", "Past Due": "orange", Grace: "orange", Suspended: "red", Cancelled: "gray" };

frappe.ui.form.on("SaaS Subscription", {
    setup(frm) {
        frm.set_query("plan", () => ({ filters: { enabled: 1 } }));
    },
    refresh(frm) {
        if (frm.is_new()) return frm.get_field("summary_html").$wrapper.empty();
        frm.page.set_indicator(__(frm.doc.status), SUB_COLORS[frm.doc.status] || "gray");
        frappe.call({ method: "stemic_control.api.subscription_summary", args: { subscription: frm.doc.name }, type: "GET" })
            .then(({ message: s }) => {
                render_subscription(frm, s);
                if (stemic_control.is_platform_admin()) add_actions(frm, s);
            });
        frm.add_custom_button(__("School"), () => frappe.set_route("Form", "SaaS Tenant", frm.doc.tenant), __("View"));
        frm.add_custom_button(__("Licenses"), () => frappe.set_route("List", "SaaS License", { subscription: frm.doc.name }), __("View"));
    },
});

function days_until(date) {
    return date ? frappe.datetime.get_diff(date, frappe.datetime.get_today()) : null;
}

function render_subscription(frm, s) {
    const d = frm.doc, fmt = (x) => frappe.datetime.str_to_user(x), esc = frappe.utils.escape_html;
    const left = days_until(d.ends_on);
    const school = esc(s.tenant.school_name || d.tenant);
    const lic = s.license;

    // What the status means and the obvious next step
    const ending = left !== null && left <= 30 && left >= 0;
    const text = {
        Trial: __("{0} is trying {1}. Activate it with the payment reference once the school pays.", [school, esc(d.plan)]),
        Active: ending ? __("Paid, but it ends in {0} days ({1}). Renew it when the school pays, then issue a new license.", [left, fmt(d.ends_on)])
            : left !== null && left < 0 ? __("The paid period ended on {0}. Renew it or mark it Past Due.", [fmt(d.ends_on)])
                : d.ends_on ? __("Paid up until {0}. Nothing to do.", [fmt(d.ends_on)]) : __("Paid up with no end date."),
        "Past Due": __("Payment is late. The school still works; move it to Grace or Suspended if it stays unpaid, or Renew when it pays."),
        Grace: __("Last chance before suspension. The school still works for now."),
        Suspended: __("Billing is suspended. Issue no new keys; the school's current key stops working when it expires. Renew to restore it."),
        Cancelled: __("This subscription is closed and cannot be renewed. Start a new subscription for the school if it returns."),
    }[d.status];
    const [color, icon] = {
        Trial: ["blue", "clock"], Active: ending || left < 0 ? ["orange", "triangle-alert"] : ["green", "check"], "Past Due": ["orange", "triangle-alert"],
        Grace: ["orange", "triangle-alert"], Suspended: ["red", "lock"], Cancelled: ["gray", "x"],
    }[d.status] || ["gray", "info"];

    // Period progress
    let period_note = "", bar = null;
    if (d.ends_on) {
        const total = Math.max(frappe.datetime.get_diff(d.ends_on, d.starts_on), 1);
        const used = Math.min(Math.max(frappe.datetime.get_diff(frappe.datetime.get_today(), d.starts_on), 0), total);
        bar = { pct: Math.round((used / total) * 100), color: left < 0 ? "red" : left <= 30 ? "orange" : "green", from: fmt(d.starts_on), to: fmt(d.ends_on) };
    } else {
        period_note = __("Started {0}, no end date", [fmt(d.starts_on)]);
    }
    const period_value = left === null ? __("Open-ended") : left >= 0 ? __("{0} days left", [left]) : __("Ended {0} days ago", [-left]);

    // License state
    let lic_value, lic_note;
    if (!lic) {
        lic_value = __("None");
        lic_note = s.licensable ? __("Use Actions > Issue License to give the school its key.") : __("Not licensable while {0}.", [__(d.status)]);
    } else {
        lic_value = `<a href="/app/saas-license/${encodeURIComponent(lic.name)}">${esc(lic.name)}</a> · ${__(lic.status)}`;
        const stale = lic.status === "Issued" && (lic.expires_on || "") !== (d.ends_on || "");
        lic_note = stale ? `<span style="color:var(--orange-600)">${__("The key's expiry ({0}) differs from this subscription. Issue a new license.", [lic.expires_on ? fmt(lic.expires_on) : __("none")])}</span>`
            : lic.status === "Issued" ? __("Issued {0}; works until {1}", [fmt(lic.issued_on), lic.expires_on ? fmt(lic.expires_on) : __("forever")])
                : __("Revoked. Issue a new license if the school needs one.");
    }

    const limit = s.plan.student_limit ? __("up to {0} students", [s.plan.student_limit]) : __("no student limit");
    frm.get_field("summary_html").$wrapper.html(`<div class="scx">
        ${stemic_control.hero(color, icon, `${school}: ${__(d.status)}`, text)}
        <div class="scx-row">
            ${stemic_control.tile(__("Subscription period"), period_value, period_note, bar)}
            ${stemic_control.tile(__("Plan"), `${esc(d.plan)} · ${stemic_control.money(s.plan.monthly_price)}<small style="display:inline">/${__("mo")}</small>`, limit)}
            ${stemic_control.tile(__("License"), lic_value, lic_note)}
            ${stemic_control.tile(__("Payment reference"), esc(d.external_payment_ref || "—"), d.agent ? __("Sold by {0}", [esc(d.agent)]) : __("Direct sale"))}
        </div>
        <div class="scx-chips"><span class="scx-chip">${__("Core")}</span>${s.modules.map((m) => `<span class="scx-chip">${esc(__(m))}</span>`).join("")}</div>
    </div>`);
}

function add_actions(frm, s) {
    const d = frm.doc, act = __("Actions");
    const call = (method, args, msg) => frappe.call({ method: `stemic_control.api.${method}`, args, freeze: true }).then((r) => {
        frappe.show_alert({ message: msg, indicator: "green" });
        frm.reload_doc();
        return r;
    });
    if (d.status !== "Cancelled") {
        frm.add_custom_button(__("Renew"), () => {
            const dlg = new frappe.ui.Dialog({
                title: __("Renew {0}", [d.school_name || d.tenant]),
                fields: [
                    { fieldname: "months", fieldtype: "Select", label: __("Extend by"), options: "1\n3\n6\n12\n24", default: "12", description: __("Months, added to the current end date (or to today if it has passed).") },
                    { fieldname: "payment_ref", fieldtype: "Data", label: __("Payment Reference"), reqd: 1 },
                    { fieldname: "issue", fieldtype: "Check", label: __("Issue a new license key for the new period"), default: s.can_sign && s.tenant.canonical_site ? 1 : 0, read_only: !(s.can_sign && s.tenant.canonical_site) },
                ],
                primary_action_label: __("Renew"),
                primary_action(v) {
                    dlg.hide();
                    call("renew_subscription", { subscription: d.name, months: v.months, payment_ref: v.payment_ref }, __("Renewed"))
                        .then(() => v.issue && issue(frm));
                },
            });
            dlg.show();
        }, act);
    }
    if (s.next.includes("Active") && d.status !== "Active") {
        frm.add_custom_button(__("Activate"), () => frappe.prompt({ fieldname: "ref", fieldtype: "Data", label: __("Payment Reference"), reqd: 1 },
            (v) => call("set_subscription_status", { subscription: d.name, status: "Active", payment_ref: v.ref }, __("Activated")), __("Activate subscription")), act);
    }
    for (const st of ["Past Due", "Grace", "Suspended", "Cancelled"]) {
        if (!s.next.includes(st)) continue;
        const label = { "Past Due": __("Mark Past Due"), Grace: __("Give Grace"), Suspended: __("Suspend"), Cancelled: __("Cancel Subscription") }[st];
        frm.add_custom_button(label, () => frappe.confirm(
            st === "Cancelled" ? __("Cancel this subscription for good? It cannot be renewed afterwards.") : __("Set this subscription to {0}?", [__(st)]),
            () => call("set_subscription_status", { subscription: d.name, status: st }, __("Now {0}", [__(st)]))), act);
    }
    if (s.licensable) {
        frm.add_custom_button(__("Issue License"), () => {
            if (!s.tenant.canonical_site) return frappe.msgprint(__("The school has no site yet. Provision it first: the key is tied to the site name."));
            if (!s.can_sign) return frappe.msgprint(__("License signing is not set up on this site. Set stemic_license_private_key_file in site_config.json to the vendor private key file."));
            frappe.confirm(__("Sign a key for {0} with the {1} plan, valid until {2}? Any earlier key of this school is marked revoked.",
                [frappe.utils.escape_html(s.tenant.school_name), frappe.utils.escape_html(d.plan), d.ends_on ? frappe.datetime.str_to_user(d.ends_on) : __("no end date")]), () => issue(frm));
        }, act);
    }
}

function issue(frm) {
    return frappe.call({ method: "stemic_control.api.issue_license", args: { subscription: frm.doc.name }, freeze: true, freeze_message: __("Signing...") })
        .then(({ message }) => frappe.set_route("Form", "SaaS License", message.license));
}
