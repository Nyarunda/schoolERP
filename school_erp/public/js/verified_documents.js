// Issue the immutable QR-stamped PDF via a deliberate staff action.
function school_issue_verified_document(frm) {
    frappe.confirm(__("Issue a new verified PDF? Any previous verification code for this document will be revoked."), () => {
        frappe.call({
            method: "school_erp.api.document_verification.issue",
            args: {doctype: frm.doctype, name: frm.doc.name},
            freeze: true,
            callback(r) {
                if (!r.message) return;
                frappe.msgprint({
                    title: __("Verified document issued"),
                    message: __("Verification code: {0}", [frappe.utils.escape_html(r.message.code)])
                        + "<p>" + __("The PDF was saved as a private attachment. Use the private file link in the document's attachments to download it.") + "</p>",
                    indicator: "green"
                });
                frm.reload_doc();
            }
        });
    });
}
frappe.ui.form.on("Fee Payment", {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frappe.user.has_role(["School Admin", "System Manager", "Bursar"])) {
            frm.add_custom_button(__("Issue Verified PDF"), () => school_issue_verified_document(frm));
        }
    }
});
frappe.ui.form.on("Report Card", {
    refresh(frm) {
        if (frm.doc.status === "Published" && frappe.user.has_role(["School Admin", "System Manager", "Head Teacher"])) {
            frm.add_custom_button(__("Issue Verified PDF"), () => school_issue_verified_document(frm));
        }
    }
});
