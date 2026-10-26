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

from school_erp import licensing

SUPPORTED = {"Fee Payment", "Report Card", "Fee Statement", "School Certificate"}
# Licensed module each document belongs to; certificates are core (always on)
MODULE = {"Fee Payment": "fees", "Report Card": "exams", "Fee Statement": "fees", "School Certificate": "core"}
ISSUER_ROLES = {"School Admin", "System Manager", "Bursar", "Head Teacher"}
ISSUE_ROLES_BY_TYPE = {
    "Fee Payment": {"School Admin", "System Manager", "Bursar"},
    "Fee Statement": {"School Admin", "System Manager", "Bursar"},
    "Report Card": {"School Admin", "System Manager", "Head Teacher"},
    "School Certificate": {"School Admin", "System Manager", "Head Teacher"},
}
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
    elif doctype == "Report Card" and doc.status != "Published":
        frappe.throw(_("Only published report cards can be verified"))
    elif doctype == "School Certificate" and doc.status != "Approved":
        frappe.throw(_("Only approved certificates can be verified"))
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
        if row.document_type == "School Certificate":
            return frappe.db.get_value("School Certificate", row.document_name, "status") == "Approved"
        if row.document_type == "Fee Statement":
            return True  # Historic, time-bound snapshot of the issued statement
    except Exception:
        return False
    return False


def _lock_source(doctype, name):
    """Serialize concurrent issuance on the underlying source row.

    Doctype identifiers are an allowlist, and the document name is SQL-bound.
    The lock is retained by Frappe until the request transaction commits.
    """
    table = {
        "Fee Payment": "tabFee Payment",
        "Report Card": "tabReport Card",
        "School Certificate": "tabSchool Certificate",
        "Fee Statement": "tabStudent",
    }[doctype]
    rows = frappe.db.sql(f"SELECT name FROM `{table}` WHERE name = %s FOR UPDATE", (name,))
    if not rows:
        frappe.throw(_("Source record does not exist"), frappe.DoesNotExistError)


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
    if source.doctype == "School Certificate":
        original = _certificate_html(source)
    elif source.doctype == "Fee Statement":
        from school_erp.api.statement import render_fee_statement
        original = render_fee_statement(source.student, source.from_date, source.to_date, full_page=True)
    else:
        original = frappe.get_print(source.doctype, source.name, as_pdf=False)
    if "</body>" in original.lower():
        position = original.lower().rfind("</body>")
        original = original[:position] + stamp + original[position:]
    else:
        original += stamp
    return get_pdf(original)


def _archive(file_name, pdf, record):
    """Store the PDF privately, byte for byte, and attach it to its Verified Document.

    frappe.utils.file_manager.save_file is not used: when File re-reads a saved file it decodes it as text
    (UTF-8, then Windows code pages) and writes it back as UTF-8, which alters some PDFs. Handing File the
    bytes as content keeps them intact; the read-back proves it, since the fingerprint must match the file."""
    file = frappe.get_doc({"doctype": "File", "file_name": file_name, "content": pdf, "is_private": 1,
                           "attached_to_doctype": "Verified Document", "attached_to_name": record.name})
    file.flags.ignore_duplicate_entry_error = True
    file.insert(ignore_permissions=True)
    with open(file.get_full_path(), "rb") as stored:
        if hashlib.sha256(stored.read()).hexdigest() != record.pdf_hash:
            frappe.throw(_("The archived PDF does not match its fingerprint; nothing was issued."))
    record.db_set("file_url", file.file_url)
    return file


@frappe.whitelist(methods=["POST"])
def issue(doctype, name):
    """Issue one private, QR-stamped PDF version. Reissues revoke previous versions."""
    if frappe.session.user == "Guest" or not (ISSUE_ROLES_BY_TYPE.get(doctype, set()) & set(frappe.get_roles())):
        frappe.throw(_("Only authorized school staff can issue this report"), frappe.PermissionError)
    licensing.require(MODULE.get(doctype, "core"), doctype)
    doc = _source(doctype, name)
    _lock_source(doctype, name)
    doc = _source(doctype, name)  # re-check state after acquiring lock
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
    record.flags.verification_issuance = True
    record.insert(ignore_permissions=True)
    file = _archive(f"{doctype.replace(' ', '_')}-{name}-{code[:8]}.pdf", pdf, record)
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
        "issuer": _issuer()}


def _issuer():
    return (frappe.get_site_config().get("school_verification_label")
            or frappe.db.get_single_value("School Settings", "school_name") or "Issuing school")


@frappe.whitelist(allow_guest=True, methods=["GET"])
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
    if not (ISSUE_ROLES_BY_TYPE.get(doc.document_type, set()) & set(frappe.get_roles())):
        frappe.throw(_("Not allowed to revoke this type of document"), frappe.PermissionError)
    if doc.document_type == "Fee Statement":
        # a statement is a snapshot, not a DocType: its name is "<student>:<from>:<to>"
        frappe.has_permission("Student", "write", doc.document_name.split(":", 1)[0], throw=True)
    else:
        frappe.has_permission(doc.document_type, "write", doc.document_name, throw=True)
    if doc.status == "Revoked":
        return {"status": "Revoked"}
    doc.db_set({"status": "Revoked", "revocation_reason": reason.strip()[:500]})
    return {"status": "Revoked"}


def _certificate_html(doc):
    import html
    settings = frappe.get_cached_doc("School Settings")
    student = frappe.get_doc("Student", doc.student)
    esc = lambda value: html.escape(str(value or ""))
    text = "<br>".join(esc(line) for line in (doc.body or "").splitlines())
    return (f"<html><body><h2>{esc(settings.school_name)}</h2>"
            f"<h3>{esc(doc.certificate_type)}</h3><p>Reference: {esc(doc.name)}</p>"
            f"<p>Date: {esc(doc.issue_date)}</p><p>Student: {esc(student.student_name)}</p>"
            f"<p>To: {esc(doc.recipient)}</p><div>{text}</div>"
            f"<p>Approved by: {esc(doc.approved_by)}</p></body></html>")


@frappe.whitelist(methods=["POST"])
def approve_certificate(name):
    if frappe.session.user == "Guest" or not ({"School Admin", "System Manager", "Head Teacher"} & set(frappe.get_roles())):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("School Certificate", name)
    doc.check_permission("write")
    if doc.status != "Draft":
        frappe.throw(_("Only draft certificates can be approved"))
    doc.db_set({"status": "Approved", "approved_by": frappe.session.user,
                "approved_on": now_datetime(), "reference_number": name})
    return {"status": "Approved"}


@frappe.whitelist(methods=["POST"])
def revoke_certificate(name, reason):
    if frappe.session.user == "Guest" or not ({"School Admin", "System Manager", "Head Teacher"} & set(frappe.get_roles())):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("School Certificate", name)
    doc.check_permission("write")
    if doc.status != "Approved" or len((reason or "").strip()) < 8:
        frappe.throw(_("Approved certificate and reason required"))
    doc.db_set("status", "Revoked")
    for code in frappe.get_all("Verified Document", filters={"document_type": "School Certificate",
            "document_name": name, "status": "Valid"}, pluck="name"):
        frappe.db.set_value("Verified Document", code, {
            "status": "Revoked", "revocation_reason": reason.strip()[:500]})
    return {"status": "Revoked"}


@frappe.whitelist(methods=["POST"])
def issue_statement(student, from_date=None, to_date=None):
    """Time-bound statement snapshot, never a live balance verification."""
    if frappe.session.user == "Guest" or not (ISSUE_ROLES_BY_TYPE["Fee Statement"] & set(frappe.get_roles())):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    licensing.require("fees", "Fee Statement")
    frappe.has_permission("Student", "read", student, throw=True)
    from school_erp.api.statement import _default_period
    from frappe.utils import getdate
    start, end = _default_period(from_date, to_date)
    if start > end or end > getdate():
        frappe.throw(_("Invalid statement date range"))
    # The reference key includes its period. Different periods are independent versions.
    key = f"{student}:{start}:{end}"
    _lock_source("Fee Statement", student)
    source = frappe._dict(doctype="Fee Statement", name=key, student=student,
                          from_date=str(start), to_date=str(end))
    code = secrets.token_urlsafe(32)
    pdf = _pdf_with_verification(source, code)
    digest = hashlib.sha256(pdf).hexdigest()
    for prior in frappe.get_all("Verified Document", filters={
        "document_type": "Fee Statement", "document_name": key, "status": "Valid"
    }, pluck="name"):
        frappe.db.set_value("Verified Document", prior, {
            "status": "Revoked", "revocation_reason": "Superseded by reissued statement"
        })
    record = frappe.get_doc({
        "doctype": "Verified Document", "verification_code": code,
        "document_type": "Fee Statement", "document_name": key,
        "issued_by": frappe.session.user, "issued_on": now_datetime(),
        "pdf_hash": digest, "status": "Valid",
    })
    record.flags.verification_issuance = True
    record.insert(ignore_permissions=True)
    file = _archive(f"Fee-Statement-{student}-{code[:8]}.pdf", pdf, record)
    return {"code": code, "verification_url": _verify_url(code), "document": record.name,
            "file_url": file.file_url}
