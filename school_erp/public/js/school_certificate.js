frappe.ui.form.on("School Certificate", {
 refresh(frm) {
  if (frm.is_new() || !["School Admin","System Manager","Head Teacher"].some(r => frappe.user.has_role(r))) return;
  if (frm.doc.status === "Draft") frm.add_custom_button(__("Approve"), () => {
   frappe.confirm(__("Approve this certificate?"), () => frappe.call({
    method:"school_erp.api.document_verification.approve_certificate",
    args:{name:frm.doc.name}, callback:()=>frm.reload_doc()
   }));
  });
  if (frm.doc.status === "Approved") {
   frm.add_custom_button(__("Issue Verified PDF"), () => frappe.call({
    method:"school_erp.api.document_verification.issue",
    args:{doctype:"School Certificate",name:frm.doc.name},
    callback:r => {if (r.message) frappe.msgprint(__("Issued. Find the PDF in private attachments. Code: {0}",[frappe.utils.escape_html(r.message.code)])); frm.reload_doc();}
   }));
   frm.add_custom_button(__("Revoke"), () => frappe.prompt([{
    fieldname:"reason",label:__("Reason"),fieldtype:"Small Text",reqd:1
   }], values => frappe.call({
    method:"school_erp.api.document_verification.revoke_certificate",
    args:{name:frm.doc.name,reason:values.reason}, callback:()=>frm.reload_doc()
   }), __("Revoke Certificate")));
  }
 }
});
