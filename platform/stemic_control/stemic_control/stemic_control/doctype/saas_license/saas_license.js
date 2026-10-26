frappe.ui.form.on("SaaS License", {
    onload(frm) {
        if (frm.is_new()) {
            frappe.msgprint(__("Licenses are signed from a subscription: open the school's subscription and use Actions > Issue License."));
            frappe.set_route("List", "SaaS Subscription");
        }
    },
    refresh(frm) {
        if (frm.is_new()) return;
        const d = frm.doc, esc = frappe.utils.escape_html, fmt = (x) => frappe.datetime.str_to_user(x);
        const demo = (d.signed_key || "").startsWith("DEMO-");
        const left = d.expires_on ? frappe.datetime.get_diff(d.expires_on, frappe.datetime.get_today()) : null;
        const grace_left = left !== null ? left + 14 : null;
        frm.page.set_indicator(__(d.status), { Issued: left !== null && left < 0 ? "orange" : "green", Revoked: "red" }[d.status] || "gray");

        let hero;
        if (demo) {
            hero = stemic_control.hero("gray", "info", __("Demo record"), __("Seeded test data with a placeholder key. It will not unlock a real school. Issue a real one from the subscription."));
        } else if (d.status === "Revoked") {
            hero = stemic_control.hero("red", "x", __("Revoked"), __("Replaced or withdrawn. Keys are checked inside the school's site without calling home, so if this key was already installed it keeps working until {0}. A newer key replaces it when pasted.",
                [d.expires_on ? fmt(frappe.datetime.add_days(d.expires_on, 14)) : __("forever (no expiry)")]));
        } else if (left !== null && left < 0) {
            hero = stemic_control.hero("orange", "triangle-alert", __("Expired"), grace_left >= 0
                ? __("Expired {0}. The school is in its 14-day grace period ({1} days left), then its records become read-only. Renew the subscription and issue a new key.", [fmt(d.expires_on), grace_left])
                : __("Expired {0}. The school's records are read-only (fee payments still work). Renew the subscription and issue a new key.", [fmt(d.expires_on)]));
        } else {
            hero = stemic_control.hero(left !== null && left <= 30 ? "orange" : "green", left !== null && left <= 30 ? "triangle-alert" : "check",
                __("Ready to install"), __("Send this key to {0} or paste it yourself on their site. It unlocks the modules below until {1}.",
                    [esc(d.school_name || d.tenant), d.expires_on ? fmt(d.expires_on) : __("no end date")]));
        }

        const term = left === null ? __("No expiry") : left >= 0 ? __("{0} days left", [left]) : __("Expired");
        const modules = (d.modules || "").split("\n").map((m) => m.trim()).filter(Boolean);
        const key = demo || !d.signed_key ? "" : `
            <div class="scx-h">${__("License key")}<span>${__("{0} characters, one line", [d.signed_key.length])}</span></div>
            <div class="scx-key"><button class="btn btn-xs btn-primary scx-copy">${__("Copy")}</button>${esc(d.signed_key)}</div>
            <ol class="scx-steps">
                <li>${__("On {0}, open {1}", [`<code>${esc(d.site || "")}</code>`, `<b>${__("School Settings > License")}</b>`])}</li>
                <li>${__("Paste the whole key into {0} and press {1}", [`<b>${__("License Key")}</b>`, `<b>${__("Save")}</b>`])}</li>
                <li>${__("The status banner turns green and the modules switch on straight away. No data is lost when a key is replaced.")}</li>
            </ol>`;

        frm.get_field("summary_html").$wrapper.html(`<div class="scx">
            ${hero}
            <div class="scx-row">
                ${stemic_control.tile(__("School"), esc(d.school_name || d.tenant), d.site ? __("Only works on {0}", [esc(d.site)]) : "")}
                ${stemic_control.tile(__("Valid until"), d.expires_on ? fmt(d.expires_on) : __("Never"), term)}
                ${stemic_control.tile(__("Plan"), esc(d.plan || "—"), d.max_students ? __("Up to {0} active students", [d.max_students]) : __("No student limit"))}
            </div>
            ${modules.length ? `<div class="scx-chips"><span class="scx-chip">${__("Core")}</span>${modules.map((m) => `<span class="scx-chip">${esc(m)}</span>`).join("")}</div>` : ""}
            ${key}
        </div>`);
        frm.get_field("summary_html").$wrapper.find(".scx-copy").on("click", () => frappe.utils.copy_to_clipboard(d.signed_key));

        frm.add_custom_button(__("Subscription"), () => frappe.set_route("Form", "SaaS Subscription", d.subscription), __("View"));
        if (d.status === "Issued" && stemic_control.is_platform_admin()) {
            if (!demo) frm.add_custom_button(__("Copy Key"), () => frappe.utils.copy_to_clipboard(d.signed_key));
            frm.add_custom_button(__("Revoke"), () => frappe.confirm(
                __("Mark this key revoked? A school that already installed it keeps working until it expires; to cut access sooner, suspend the school."),
                () => frappe.call({ method: "stemic_control.api.revoke_license", args: { license: d.name } }).then(() => frm.reload_doc())), __("Actions"));
        }
    },
});
