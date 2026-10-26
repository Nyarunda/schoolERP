"""Tenant-local, minimal-disclosure verification for issued school PDF documents.

The issued PDF (including its QR reference) is stored privately; its SHA-256 is immutable.
Public callers cannot read source records or fetch private files.
"""
import base64
import hashlib
import io
import re
import secrets
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import get_url, now_datetime
from frappe.utils.file_manager import save_file

SUPPORTED = {"Fee Payment", "Report Card"}
ISSUER_ROLES = {"School Admin", "System Manager", "Bursar", "Head Teacher"}
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,100}$")
HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _source(doctype, name):
    if doctype not in SUPPORTED:
        frappe.throw(_("Unsupported verification document type"), frappe.ValidationError)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("print")
    if doctype == "Fee Payment":
        if doc.docstatus != 1 or not doc.payment_entry:
            frappe.throw(_("Fee Payment must be posted before issuing a verified receipt"))
        if frappe.db.get_value("Payment Entry", doc.payment_entry, "docstatus") != 1:
            frappe.throw(_("Linked accounting Payment Entry is not submitted"))
    elif doc.status != "Published":
        frappe.throw(_("Only published report cards can be verified"))
    return doc


def _is_current(row):
    try:
        if row.document_type == "Fee Payment":
            status, payment_entry = frappe.db.get_value(
                "Fee Payment", row.document_name, ["docstatus", "payment_entry"]
            ) or (None, None)
            return status == 1 and bool(payment_entry) and frappe.db.get_value(
                "Payment Entry", payment_entry, "docstatus"
            ) == 1
        if row.document_type == "Report Card":
            return frappe.db.get_value("Report Card", row.document_name, "status") == "Published"
    except Exception:
        return False
    return False


def _verify_url(code):
    # This site's HTTPS host must be configured accurately in production.
    return get_url("/verify?code=" + quote(code, safe=""))


def _qr_data(url):
    import qrcode
    image = qrcode.make(url)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _pdf_with_verification(source, code):
    import html
    from frappe.utils.pdf import get_pdf

    url = _verify_url(code)
    qr = _qr_data(url)
    stamp = (
        '<div style="page-break-inside:avoid;margin:28px 0;padding:12px;'
        'border-top:1px solid #999;font-family:sans-serif;font-size:10px">'
        '<table><tr><td style="width:105px"><img width="92" height="92" src="' + qr + '"></td>'
        '<td><b>Verify this issued document</b><p>Code: ' + html.escape(code) +
        '</p><p>' + html.escape(url) +
        '</p><small>Check this exact PDF on the official verification page.</small></td></tr></table></div>'
    )
    original = frappe.get_print(source.doctype, source.name, as_pdf=False)
    if "</body>" in original.lower():
        position = original.lower().rfind("</body>")
        original = original[:position] + stamp + original[position:]
    else:
        original += stamp
    return get_pdf(original)


@frappe.whitelist(methods=["POST"])
def issue(doctype, name):
    """Issue one private, QR-stamped PDF version. Reissues revoke previous versions."""
    if frappe.session.user == "Guest" or not (ISSUER_ROLES & set(frappe.get_roles())):
        frappe.throw(_("Only authorized school staff can issue verified reports"), frappe.PermissionError)
    doc = _source(doctype, name)
    code = secrets.token_urlsafe(32)
    pdf = _pdf_with_verification(doc, code)
    digest = hashlib.sha256(pdf).hexdigest()
    old = frappe.get_all("Verified Document", filters={"document_type": doctype,
        "document_name": name, "status": "Valid"}, pluck="name")
    for prior in old:
        frappe.db.set_value("Verified Document", prior, {
            "status": "Revoked", "revocation_reason": "Superseded by reissued document"
        })
    record = frappe.get_doc({
        "doctype": "Verified Document", "verification_code": code,
        "document_type": doctype, "document_name": name, "issued_by": frappe.session.user,
        "issued_on": now_datetime(), "pdf_hash": digest, "status": "Valid"
    })
    record.insert(ignore_permissions=True)
    file = save_file(f"{doctype.replace(' ', '_')}-{name}-{code[:8]}.pdf",
        pdf, "Verified Document", record.name, is_private=1)
    record.db_set("file_url", file.file_url)
    return {"code": code, "verification_url": _verify_url(code),
        "file_url": file.file_url, "document": record.name}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def verify(code=None):
    """Public, tenant-local status only. No names, marks, balances, phone or private URL."""
    if not isinstance(code, str) or not CODE_PATTERN.fullmatch(code):
        return {"status": "Not Found"}
    row = frappe.db.get_value("Verified Document", code,
        ["document_type", "document_name", "status", "issued_on"], as_dict=True)
    if not row:
        return {"status": "Not Found"}
    state = "Valid" if row.status == "Valid" and _is_current(row) else "Revoked"
    return {"status": state, "document_type": row.document_type,
        "issued_on": str(row.issued_on) if row.issued_on else None,
        "issuer": frappe.get_site_config().get("school_verification_label") or "Issuing school"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def verify_hash(code=None, sha256=None):
    """Compare a browser-computed SHA-256 against the exact archived PDF without uploading it."""
    if not isinstance(code, str) or not CODE_PATTERN.fullmatch(code):
        return {"status": "Not Found", "matches": False}
    if not isinstance(sha256, str) or not HASH_PATTERN.fullmatch(sha256):
        return {"status": "Invalid Input", "matches": False}
    row = frappe.db.get_value("Verified Document", code,
        ["document_type", "document_name", "status", "pdf_hash"], as_dict=True)
    if not row:
        return {"status": "Not Found", "matches": False}
    if row.status != "Valid" or not _is_current(row):
        return {"status": "Revoked", "matches": False}
    return {"status": "Valid", "matches": secrets.compare_digest(row.pdf_hash.lower(), sha256.lower())}


@frappe.whitelist(methods=["POST"])
def revoke(code, reason):
    if frappe.session.user == "Guest" or not (ISSUER_ROLES & set(frappe.get_roles())):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if not reason or len(reason.strip()) < 8:
        frappe.throw(_("Provide a revocation reason (at least eight characters)"))
    doc = frappe.get_doc("Verified Document", code)
    frappe.has_permission(doc.document_type, "write", doc.document_name, throw=True)
    if doc.status == "Revoked":
        return {"status": "Revoked"}
    doc.db_set({"status": "Revoked", "revocation_reason": reason.strip()[:500]})
    return {"status": "Revoked"}
