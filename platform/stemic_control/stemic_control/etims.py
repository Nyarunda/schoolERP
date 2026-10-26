"""Reviewed tax invoices and controlled certified-provider integration boundary."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime, cint

from stemic_control.tax_rules import valid_pin, validate_amounts

INVOICE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,89}$")


def _admin():
    if frappe.session.user == "Guest" or not ({"System Manager", "Stemic Platform Admin"} & set(frappe.get_roles())):
        frappe.throw(_("Platform tax administrator access required"), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def prepare_invoice(tenant, external_invoice_no, buyer_name, net_amount, vat_amount,
                    total_amount, tax_treatment, subscription=None, buyer_pin=None, seller_scope="School"):
    """Capture reviewed billable supply without creating a fictional KRA acknowledgement."""
    _admin()
    if not INVOICE_REF.fullmatch(str(external_invoice_no or "")):
        frappe.throw(_("Invalid source invoice reference"))
    if not frappe.db.exists("SaaS Tenant", tenant):
        frappe.throw(_("Unknown customer"))
    if seller_scope == "School":
        profile = frappe.db.get_value("SaaS Tax Profile", {"tenant": tenant},
            ["name", "seller_pin", "enabled"], as_dict=True)
    elif seller_scope == "Stemic Platform":
        profile = frappe.db.get_singles_dict("Stemic Tax Settings")
        if subscription is None:
            frappe.throw(_("Platform tax invoices must reference a subscription"))
    else:
        frappe.throw(_("Unknown legal seller"))
    if not profile or not cint(profile.get("enabled")) or not valid_pin(profile.get("seller_pin")):
        frappe.throw(_("Enable the legal seller tax profile and verify its KRA PIN first"))
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
    source = {"tenant": tenant, "seller_scope": seller_scope, "external_invoice_no": external_invoice_no,
        "buyer_name": buyer_name.strip(), "buyer_pin": (buyer_pin or "").upper(),
        "seller_pin": profile.seller_pin.upper(), "net_amount": str(net),
        "vat_amount": str(tax), "total_amount": str(total),
        "tax_treatment": tax_treatment, "subscription": subscription or ""}
    digest = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    invoice_key = "ETI-" + hashlib.sha256(f"{seller_scope}|{tenant}|{external_invoice_no}".encode()).hexdigest().upper()[:40]
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
def prepare_platform_subscription_invoice(subscription, external_invoice_no, net_amount,
                                          vat_amount, total_amount, tax_treatment,
                                          buyer_pin=None):
    """Prepare Stemic-as-seller invoicing for a school subscription.

    Pricing/tax totals must originate from the approved accounting invoice,
    not the subscription plan's price alone.
    """
    _admin()
    sub = frappe.get_doc("SaaS Subscription", subscription)
    if not sub.tenant:
        frappe.throw(_("Subscription has no school customer"))
    school_name = frappe.db.get_value("SaaS Tenant", sub.tenant, "school_name")
    if not school_name:
        frappe.throw(_("Unknown school customer"))
    return prepare_invoice(tenant=sub.tenant, subscription=sub.name,
        external_invoice_no=external_invoice_no, buyer_name=school_name,
        buyer_pin=buyer_pin, net_amount=net_amount, vat_amount=vat_amount,
        total_amount=total_amount, tax_treatment=tax_treatment,
        seller_scope="Stemic Platform")


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
    _audit(name, "Tax review approved", "Draft", "Ready")
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
            "live_submission_enabled": bool(frappe.conf.get("stemic_etims_live_enabled"))}


def _audit(invoice, event_type, old_status=None, new_status=None, details=""):
    event = frappe.get_doc({"doctype": "SaaS eTIMS Event", "invoice": invoice,
        "event_type": event_type, "old_status": old_status,
        "new_status": new_status, "details": str(details or "")[:500],
        "recorded_on": now_datetime(), "actor": frappe.session.user})
    event.flags.etims_event = True
    event.insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def queue_submission(name):
    """Queue approved invoice for the configured audited provider adapter."""
    _admin()
    doc = frappe.get_doc("SaaS eTIMS Invoice", name, for_update=True)
    if doc.status != "Ready":
        frappe.throw(_("Invoice must be reviewed and Ready"))
    if not frappe.conf.get("stemic_etims_live_enabled") or not frappe.conf.get("stemic_etims_adapter"):
        frappe.throw(_("Certified provider not configured; no invoice was transmitted"))
    previous = doc.status
    doc.db_set({"status": "Pending Submission", "last_error": ""})
    _audit(name, "Queued for provider", previous, "Pending Submission")
    frappe.enqueue("stemic_control.etims.submit_queued", name=name, queue="short",
                   enqueue_after_commit=True, job_id="stemic-etims-" + name)
    return {"name": name, "status": "Pending Submission", "kra_submitted": False}


def submit_queued(name):
    """Worker-only execution. A timeout is not rejection: retain Pending Submission."""
    import importlib

    if not frappe.conf.get("stemic_etims_live_enabled"):
        return {"status": "Disabled"}
    adapter_path = frappe.conf.get("stemic_etims_adapter") or ""
    if not re.fullmatch(r"[a-z_][a-z_0-9]*(?:\.[a-z_][a-z_0-9]*)+", adapter_path):
        frappe.throw(_("Invalid integration adapter path"))
    # Restrict registered adapter to deployment-controlled code, never a user-supplied method path.
    if not adapter_path.startswith("stemic_control_integrations."):
        frappe.throw(_("Adapter must be installed under stemic_control_integrations"))
    doc = frappe.get_doc("SaaS eTIMS Invoice", name, for_update=True)
    if doc.status != "Pending Submission":
        return {"status": doc.status}
    module_name, fn_name = adapter_path.rsplit(".", 1)
    fn = getattr(importlib.import_module(module_name), fn_name)
    payload = {field: doc.get(field) for field in (
        "invoice_key", "external_invoice_no", "seller_scope", "seller_pin", "tenant",
        "buyer_name", "buyer_pin", "tax_treatment", "currency", "net_amount",
        "vat_amount", "total_amount", "source_payload_hash")}
    # Adapter must implement idempotent submission AND lookup by invoice_key.
    # Its result has an explicit, verified evidence contract; ordinary HTTP 200 is not proof.
    try:
        result = fn(payload)
    except Exception:
        frappe.log_error(title="eTIMS provider transport failed for " + name)
        _audit(name, "Transport uncertain", "Pending Submission", "Pending Submission",
               "Provider transport failed; reconcile before retry")
        return {"status": "Pending Submission"}
    if not isinstance(result, dict) or result.get("status") not in ("accepted", "rejected", "pending"):
        frappe.throw(_("Invalid certified provider response"))
    if result["status"] == "accepted":
        if not all(str(result.get(key) or "").strip() for key in (
            "provider_reference", "kra_invoice_number", "verification_evidence")):
            frappe.throw(_("Provider accepted result has no authenticated KRA evidence"))
        if not result.get("signature_verified") is True:
            frappe.throw(_("Provider acceptance is not verified"))
        doc.db_set({"status": "Submitted", "provider_reference": str(result["provider_reference"])[:140],
                    "kra_invoice_number": str(result["kra_invoice_number"])[:140],
                    "submitted_on": now_datetime(), "last_error": ""})
        _audit(name, "Provider accepted", "Pending Submission", "Submitted",
               str(result["verification_evidence"])[:450])
        return {"status": "Submitted"}
    if result["status"] == "rejected":
        doc.db_set({"status": "Rejected", "last_error": str(result.get("reason") or "Provider rejected")[:500]})
        _audit(name, "Provider rejected", "Pending Submission", "Rejected", result.get("reason"))
        return {"status": "Rejected"}
    _audit(name, "Provider pending", "Pending Submission", "Pending Submission")
    return {"status": "Pending Submission"}


@frappe.whitelist(methods=["GET"])
def invoice_history(name):
    _admin()
    return frappe.get_all("SaaS eTIMS Event", filters={"invoice": name},
        fields=["event_type", "old_status", "new_status", "details", "recorded_on"],
        order_by="recorded_on desc", limit_page_length=100)


@frappe.whitelist(methods=["GET"])
def reconciliation_summary():
    _admin()
    return {"ready": frappe.db.count("SaaS eTIMS Invoice", {"status": "Ready"}),
            "pending": frappe.db.count("SaaS eTIMS Invoice", {"status": "Pending Submission"}),
            "rejected": frappe.db.count("SaaS eTIMS Invoice", {"status": "Rejected"}),
            "confirmed": frappe.db.count("SaaS eTIMS Invoice", {"status": "Submitted"}),
            "adapter_configured": bool(frappe.conf.get("stemic_etims_adapter")),
            "transmission_enabled": bool(frappe.conf.get("stemic_etims_live_enabled"))}


@frappe.whitelist(methods=["POST"])
def reconcile_invoice(name):
    """Lookup-only reconciliation for uncertain provider submissions; never resends an invoice."""
    import importlib

    _admin()
    if not frappe.conf.get("stemic_etims_live_enabled"):
        frappe.throw(_("Provider integration is disabled"))
    method = frappe.conf.get("stemic_etims_lookup_adapter") or ""
    if not method.startswith("stemic_control_integrations.") or not re.fullmatch(
        r"[a-z_][a-z_0-9]*(?:\.[a-z_][a-z_0-9]*)+", method
    ):
        frappe.throw(_("Certified provider lookup adapter not configured"))
    doc = frappe.get_doc("SaaS eTIMS Invoice", name, for_update=True)
    if doc.status != "Pending Submission":
        return {"status": doc.status}
    module, function = method.rsplit(".", 1)
    lookup = getattr(importlib.import_module(module), function)
    result = lookup({"invoice_key": doc.invoice_key, "provider_reference": doc.provider_reference,
                     "seller_pin": doc.seller_pin, "seller_scope": doc.seller_scope})
    if not isinstance(result, dict):
        frappe.throw(_("Invalid provider lookup response"))
    if result.get("status") == "accepted":
        if result.get("signature_verified") is not True or not all(
            str(result.get(key) or "").strip() for key in
            ("verification_evidence", "provider_reference", "kra_invoice_number")
        ):
            frappe.throw(_("Provider lookup lacks verified acceptance evidence"))
        doc.db_set({"status": "Submitted", "provider_reference": str(result["provider_reference"])[:140],
                    "kra_invoice_number": str(result["kra_invoice_number"])[:140],
                    "submitted_on": now_datetime(), "last_error": ""})
        _audit(name, "Provider lookup confirmed", "Pending Submission", "Submitted",
               str(result["verification_evidence"])[:450])
        return {"status": "Submitted"}
    if result.get("status") == "rejected" and result.get("signature_verified") is True:
        reason = str(result.get("reason") or "Provider rejected")[:500]
        doc.db_set({"status": "Rejected", "last_error": reason})
        _audit(name, "Provider lookup rejected", "Pending Submission", "Rejected", reason)
        return {"status": "Rejected"}
    _audit(name, "Provider lookup pending", "Pending Submission", "Pending Submission")
    return {"status": "Pending Submission"}
