// Issue the immutable QR-stamped PDF via a deliberate staff action.
frappe.provide("school_erp");

// What staff see once a verified PDF exists: open it, and the link anyone can use to check it
school_erp.show_verified_document = function (r) {
    const esc = frappe.utils.escape_html;
    frappe.msgprint({
        title: __("Verified document issued"),
        indicator: "green",
        message: `<p><a class="btn btn-sm btn-primary" href="${esc(r.file_url)}" target="_blank">${__("Open PDF")}</a></p>
            <p>${__("Print or send this exact PDF. Anyone can scan its QR code, or open the link below, to check it is genuine.")}</p>
            <p class="small"><a href="${esc(r.verification_url)}" target="_blank">${esc(r.verification_url)}</a></p>
            <p class="small text-muted">${__("Issuing it again revokes this copy. The PDF is kept privately under Verified Documents.")}</p>`,
    });
};

function school_issue_verified_document(frm) {
    frappe.confirm(__("Issue a new verified PDF? Any previous verification code for this document will be revoked."), () => {
        frappe.call({
            method: "school_erp.api.document_verification.issue",
            args: {doctype: frm.doctype, name: frm.doc.name},
            freeze: true,
            freeze_message: __("Creating PDF..."),
            callback(r) {
                if (!r.message) return;
                school_erp.show_verified_document(r.message);
                frm.reload_doc();
            }
        });
    });
}
frappe.ui.form.on("Fee Payment", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && ["School Admin", "System Manager", "Bursar"].some(role => frappe.user.has_role(role))) {
            frm.add_custom_button(__("Issue Verified PDF"), () => school_issue_verified_document(frm));
        }
    }
});
frappe.ui.form.on("Report Card", {
    refresh(frm) {
        if (frm.doc.status === "Published" && ["School Admin", "System Manager", "Head Teacher"].some(role => frappe.user.has_role(role))) {
            frm.add_custom_button(__("Issue Verified PDF"), () => school_issue_verified_document(frm));
        }
    }
});
