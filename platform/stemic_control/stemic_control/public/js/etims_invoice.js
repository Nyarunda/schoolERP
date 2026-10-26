frappe.ui.form.on("SaaS eTIMS Invoice", {
 refresh(frm) {
   if (frm.is_new() || !["System Manager", "Stemic Platform Admin"].some(r => frappe.user.has_role(r))) return;
   if (frm.doc.status === "Draft") {
     frm.add_custom_button(__("Approve Tax Review"), () => frappe.confirm(
       __("Confirm the legal seller, tax classification and totals have been checked."),
       () => frappe.call({method:"stemic_control.etims.approve_invoice",
         args:{name:frm.doc.name}, callback:()=>frm.reload_doc()})
     ));
   }
   if (frm.doc.status === "Ready") {
     frm.add_custom_button(__("Queue eTIMS Submission"), () => frappe.confirm(
       __("Send this reviewed invoice to the configured certified integration?"),
       () => frappe.call({method:"stemic_control.etims.queue_submission",
         args:{name:frm.doc.name}, callback:()=>frm.reload_doc()})
     ));
   }
   if (frm.doc.status === "Pending Submission") {
     frm.add_custom_button(__("Reconcile With Provider"), () => frappe.confirm(
       __("Query provider status without submitting the invoice again?"),
       () => frappe.call({method:"stemic_control.etims.reconcile_invoice",
          args:{name:frm.doc.name},callback:()=>frm.reload_doc()})
     ));
   }
   frm.add_custom_button(__("Submission History"), () => frappe.call({
     method:"stemic_control.etims.invoice_history", args:{name:frm.doc.name},
     callback:r => frappe.msgprint({title:__("Tax Submission History"),
       message:"<pre>"+frappe.utils.escape_html(JSON.stringify(r.message || [],null,2))+"</pre>",
       wide:true})
   }));
 }
});
