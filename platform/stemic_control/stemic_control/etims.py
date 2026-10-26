"""eTIMS preparation and review. No live KRA submission is performed by this module."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from stemic_control.tax_rules import valid_pin, validate_amounts

INVOICE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,89}$")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw(_("Platform tax administrator access required"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def prepare_invoice(tenant, external_invoice_no, buyer_name, net_amount, vat_amount,
                    total_amount, tax_treatment, subscription=None, buyer_pin=None):
    """Capture reviewed billable supply without creating a fictional KRA acknowledgement."""
    _admin()
    if not INVOICE_REF.fullmatch(str(external_invoice_no or "")):
        frappe.throw(_("Invalid source invoice reference"))
    if not frappe.db.exists("SaaS Tenant", tenant):
        frappe.throw(_("Unknown customer"))
    profile = frappe.db.get_value("SaaS Tax Profile", {"tenant": tenant},
        ["name", "seller_pin", "enabled"], as_dict=True)
    if not profile or not profile.enabled or not valid_pin(profile.seller_pin):
        frappe.throw(_("Enable a tax profile with a valid seller KRA PIN first"))
    if buyer_pin and not valid_pin(buyer_pin):
        frappe.throw(_("Invalid buyer KRA PIN"))
    if not str(buyer_name or "").strip():
        frappe.throw(_("Buyer name required"))
    if subscription and frappe.db.get_value("SaaS Subscription", subscription, "tenant") != tenant:
        frappe.throw(_("Subscription belongs to another customer"), frappe.PermissionError)
    try:
        net, tax, total = validate_amounts(net_amount, vat_amount, total_amount, tax_treatment)
    except ValueError as error:
        frappe.throw(str(error))
    source = {"tenant": tenant, "external_invoice_no": external_invoice_no,
        "buyer_name": buyer_name.strip(), "buyer_pin": (buyer_pin or "").upper(),
        "seller_pin": profile.seller_pin.upper(), "net_amount": str(net),
        "vat_amount": str(tax), "total_amount": str(total),
        "tax_treatment": tax_treatment, "subscription": subscription or ""}
    digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    invoice_key = "ETI-" + hashlib.sha256(f"{tenant}|{external_invoice_no}".encode()).hexdigest().upper()[:40]
    existing = frappe.db.get_value("SaaS eTIMS Invoice", invoice_key,
        ["name", "source_payload_hash"], as_dict=True)
    if existing:
        if existing.source_payload_hash != digest:
            frappe.throw(_("Source invoice changed; investigate before issuing another version"))
        return {"name": existing.name, "status": frappe.db.get_value("SaaS eTIMS Invoice", existing.name, "status")}
    doc = frappe.get_doc({"doctype": "SaaS eTIMS Invoice", **source,
        "currency": "KES", "status": "Draft", "source_payload_hash": digest,
        "invoice_key": invoice_key})
    doc.flags.etims_service = True
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "status": "Draft"}


@frappe.whitelist(methods=["POST"])
def approve_invoice(name):
    """Approve for integration; does not contact the tax authority."""
    _admin()
    doc = frappe.get_doc("SaaS eTIMS Invoice", name)
    if doc.status != "Draft":
        frappe.throw(_("Only draft tax invoices can be reviewed"))
    if not valid_pin(doc.seller_pin):
        frappe.throw(_("Seller KRA PIN is invalid"))
    try:
        validate_amounts(doc.net_amount, doc.vat_amount, doc.total_amount, doc.tax_treatment)
    except ValueError as error:
        frappe.throw(str(error))
    doc.db_set({"status": "Ready", "reviewed_by": frappe.session.user, "reviewed_on": now_datetime()})
    return {"name": name, "status": "Ready", "kra_submitted": False}


@frappe.whitelist(methods=["GET"])
def compliance_overview():
    _admin()
    count = frappe.db.count
    return {"draft": count("SaaS eTIMS Invoice", {"status": "Draft"}),
            "ready": count("SaaS eTIMS Invoice", {"status": "Ready"}),
            "pending": count("SaaS eTIMS Invoice", {"status": "Pending Submission"}),
            "submitted": count("SaaS eTIMS Invoice", {"status": "Submitted"}),
            "rejected": count("SaaS eTIMS Invoice", {"status": "Rejected"}),
            "profiles": count("SaaS Tax Profile", {"enabled": 1}),
            "live_submission_enabled": False}
