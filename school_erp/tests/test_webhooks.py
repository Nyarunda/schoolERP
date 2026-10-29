"""Outbound webhooks: destination checks, the pinned HTTPS transport (against a real local TLS receiver), DNS rebinding,
producers and permissions.
bench --site <site> run-tests --module school_erp.tests.test_webhooks"""

import datetime
import hashlib
import hmac
import http.server
import json
import os
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch

import frappe

from school_erp.api import webhooks
from school_erp.tests.test_integration import TestCase, setup_school

PUBLIC = "93.184.216.34"
HOST = "hooks.example.test"


class TestWebhookTargets(unittest.TestCase):
	def test_signature(self):
		self.assertEqual(webhooks.sign('{"x":1}', 'test-secret'),
						 hmac.new(b'test-secret', b'{"x":1}', hashlib.sha256).hexdigest())

	@patch("school_erp.api.webhooks.frappe.throw", side_effect=ValueError)
	def test_reject_http_ports_and_credentials(self, _):
		for url in ("http://example.com/hook", "https://example.com:8443/hook", "https://u:p@example.com/hook",
					"https://localhost/hook", "https://printer.local/hook"):
			with self.subTest(url=url), self.assertRaises(ValueError):
				webhooks.validate_target(url)

	@patch("school_erp.api.webhooks.frappe.throw", side_effect=ValueError)
	def test_reject_any_non_public_address(self, _):
		for addresses in (["127.0.0.1"], ["10.1.2.3"], ["169.254.169.254"], ["::1"], ["::ffff:127.0.0.1"],
						  ["fd00::1"], [PUBLIC, "192.168.1.5"], []):
			with self.subTest(addresses=addresses), patch("school_erp.api.webhooks._lookup", return_value=addresses), \
					self.assertRaises(ValueError):
				webhooks.validate_target("https://example.org/event")

	@patch("school_erp.api.webhooks._lookup", return_value=[PUBLIC])
	def test_public_https_target(self, _):
		self.assertEqual(webhooks.validate_target("https://example.org/event"), "https://example.org/event")
		self.assertEqual(webhooks.resolve_target("https://Example.org./event"), ("example.org", PUBLIC))


def _certificate(directory):
	"""A self-signed certificate for HOST, written as cert.pem and key.pem."""
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import ec
	from cryptography.x509.oid import NameOID

	key = ec.generate_private_key(ec.SECP256R1())
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
	now = datetime.datetime.now(datetime.timezone.utc)
	cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
			.serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
			.not_valid_after(now + datetime.timedelta(days=1))
			.add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False)
			.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
			.sign(key, hashes.SHA256()))
	paths = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
	with open(paths[0], "wb") as f:
		f.write(cert.public_bytes(serialization.Encoding.PEM))
	with open(paths[1], "wb") as f:
		f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
								  serialization.NoEncryption()))
	return paths


class _Receiver(http.server.BaseHTTPRequestHandler):
	def do_POST(self):
		body = self.rfile.read(int(self.headers["Content-Length"]))
		self.server.received.append({"path": self.path, "headers": dict(self.headers), "body": body.decode(),
									 "sni": getattr(self.connection, "server_hostname", None)})
		self.send_response(self.server.reply)
		self.end_headers()
		self.wfile.write(b"ok")

	def log_message(self, *args):
		pass


class TestWebhookDelivery(TestCase):
	"""Deliveries to a real HTTPS server on 127.0.0.1. It stands in for a public receiver: the address check is
	relaxed for loopback only where a test says so, and the server's certificate is trusted for those tests."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		cls._dir = tempfile.TemporaryDirectory()
		cls.cert, key = _certificate(cls._dir.name)
		context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
		context.load_cert_chain(cls.cert, key)
		snis = []
		context.sni_callback = lambda sock, name, ctx: snis.append(name)
		cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Receiver)
		cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
		cls.server.received, cls.server.reply, cls.snis = [], 200, snis
		cls.server.handle_error = lambda *args: None  # handshakes the client refuses (wrong certificate) are expected
		threading.Thread(target=cls.server.serve_forever, daemon=True).start()

	@classmethod
	def tearDownClass(cls):
		cls.server.shutdown()
		cls.server.server_close()
		cls._dir.cleanup()
		cls._pub.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.server.received.clear()
		self.snis.clear()
		self.server.reply = 200
		# deliver() commits its "Sending" mark; keep everything inside the test's transaction instead
		self._commit = patch.object(frappe.db, "commit")
		self._commit.start()
		self._port = patch.object(webhooks, "PORT", self.server.server_address[1])
		self._port.start()
		self._ca = patch.object(webhooks, "_ca_bundle", return_value=self.cert)
		self._ca.start()

	def tearDown(self):
		self._ca.stop()
		self._port.stop()
		self._commit.stop()
		frappe.db.rollback()

	def endpoint(self, url=f"https://{HOST}/stemic/events?school=1", events="student.created", **kw):
		with patch.object(webhooks, "_lookup", return_value=[PUBLIC]):
			return frappe.get_doc({"doctype": webhooks.ENDPOINT, "endpoint_url": url, "enabled": 1,
								   "event_types": events, "secret": "receiver-secret", **kw}).insert()

	def queued(self, endpoint, event_id=None):
		event_id = event_id or frappe.generate_hash(length=10)
		with patch.object(webhooks.frappe, "enqueue"):
			webhooks.publish(event_id, "student.created", {"id": event_id, "data": {"student": "STU-1"}})
		return frappe.get_value(webhooks.DELIVERY, {"endpoint": endpoint.name, "event_id": event_id}, "name")

	def test_delivers_signed_body_to_the_pinned_address(self):
		name = self.queued(self.endpoint())
		with patch.object(webhooks, "_lookup", return_value=["127.0.0.1"]) as lookup, \
				patch.object(webhooks, "_is_public", return_value=True):
			webhooks.deliver(name)
		lookup.assert_called_once_with(HOST)  # one DNS answer per delivery: nothing re-resolves the name
		delivery = frappe.get_doc(webhooks.DELIVERY, name)
		self.assertEqual((delivery.status, delivery.response_code, delivery.attempts), ("Accepted", 200, 1))
		[request] = self.server.received
		self.assertEqual(request["path"], "/stemic/events?school=1")
		self.assertEqual(request["headers"]["Host"], HOST)
		self.assertEqual(self.snis, [HOST])  # TLS names the real host, and its certificate was verified for it
		self.assertEqual(request["body"], delivery.payload)
		self.assertEqual(request["headers"]["X-Stemic-Signature-SHA256"], webhooks.sign(delivery.payload, "receiver-secret"))
		self.assertEqual(request["headers"]["X-Stemic-Delivery"], name)
		self.assertEqual(request["headers"]["X-Stemic-Event"], "student.created")

	def test_rebinding_to_a_private_address_is_refused_before_connecting(self):
		"""The name was public when the endpoint was saved; at delivery it answers 127.0.0.1."""
		name = self.queued(self.endpoint())
		with patch.object(webhooks, "_lookup", return_value=["127.0.0.1"]):
			webhooks.deliver(name)
		delivery = frappe.get_doc(webhooks.DELIVERY, name)
		self.assertEqual(delivery.status, "Retrying")
		self.assertIn("non-public", delivery.error)
		self.assertEqual(self.server.received, [])

	def test_certificate_must_match_the_name(self):
		"""Pinning the address does not weaken TLS: a certificate for another name is refused."""
		name = self.queued(self.endpoint(url="https://other.example.test/hook"))
		with patch.object(webhooks, "_lookup", return_value=["127.0.0.1"]), \
				patch.object(webhooks, "_is_public", return_value=True):
			webhooks.deliver(name)
		delivery = frappe.get_doc(webhooks.DELIVERY, name)
		self.assertEqual(delivery.status, "Retrying")
		self.assertEqual(self.server.received, [])

	def test_failures_retry_then_stop(self):
		self.server.reply = 500
		name = self.queued(self.endpoint(max_attempts=2))
		with patch.object(webhooks, "_lookup", return_value=["127.0.0.1"]), \
				patch.object(webhooks, "_is_public", return_value=True):
			webhooks.deliver(name)
			self.assertEqual(frappe.db.get_value(webhooks.DELIVERY, name, "status"), "Retrying")
			webhooks.deliver(name)
		delivery = frappe.get_doc(webhooks.DELIVERY, name)
		self.assertEqual((delivery.status, delivery.attempts, delivery.next_attempt_at), ("Failed", 2, None))
		self.assertIn("HTTP 500", delivery.error)
		self.assertEqual(len(self.server.received), 2)

	def test_one_delivery_per_endpoint_and_event(self):
		endpoint = self.endpoint()
		event_id = frappe.generate_hash(length=10)
		self.queued(endpoint, event_id)
		self.queued(endpoint, event_id)
		self.assertEqual(frappe.db.count(webhooks.DELIVERY, {"endpoint": endpoint.name, "event_id": event_id}), 1)

	# ------------------------------------------------------------------ producers
	def deliveries(self, event_type):
		return [json.loads(p) for p in frappe.get_all(webhooks.DELIVERY, filters={"event_type": event_type}, pluck="payload")]

	def test_new_student_publishes_a_thin_event(self):
		self.endpoint()
		with patch.object(webhooks.frappe, "enqueue") as enqueue:
			student = frappe.get_doc({"doctype": "Student", "first_name": "hook", "last_name": "test",
									  "stream": "Grade 4 Test", "guardians": [{"guardian_name": "Grace Test",
																			   "relation": "Mother", "mobile_no": "0712345678"}]}).insert()
		[event] = [e for e in self.deliveries("student.created") if e["data"]["student"] == student.name]
		self.assertEqual(event["id"], f"Student:{student.name}:student.created")
		self.assertEqual(event["site"], frappe.local.site)
		self.assertEqual(set(event["data"]), {"student", "school_class"})  # no names, phones or guardians
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

	def test_fee_payment_and_invoice_events(self):
		self.endpoint(events="fee_payment.posted\ninvoice.submitted")
		with patch.object(webhooks.frappe, "enqueue"):
			webhooks.on_fee_payment_submit(frappe._dict(doctype="Fee Payment", name="RCPT-HOOK-1", student="STU-1",
														posting_date="2026-10-28", amount=500))
			webhooks.on_sales_invoice_submit(frappe._dict(doctype="Sales Invoice", name="SINV-HOOK-1", student="STU-1",
														  school_term="T1", posting_date="2026-10-28"))
			webhooks.on_sales_invoice_submit(frappe._dict(doctype="Sales Invoice", name="SINV-HOOK-2", student=None,
														  posting_date="2026-10-28"))
		[payment] = self.deliveries("fee_payment.posted")
		self.assertEqual(payment["data"], {"fee_payment": "RCPT-HOOK-1", "student": "STU-1", "posting_date": "2026-10-28"})
		[invoice] = self.deliveries("invoice.submitted")  # the invoice without a student is not a school event
		self.assertEqual(invoice["data"]["invoice"], "SINV-HOOK-1")

	def test_unsubscribed_or_disabled_endpoints_get_nothing(self):
		self.endpoint(events="invoice.submitted")
		self.endpoint(enabled=0)
		with patch.object(webhooks.frappe, "enqueue"):
			webhooks.on_student_insert(frappe._dict(doctype="Student", name="STU-NONE", school_class=None))
		self.assertEqual(self.deliveries("student.created"), [])

	def test_a_webhook_failure_never_blocks_the_school(self):
		self.endpoint()
		with patch.object(webhooks, "publish", side_effect=RuntimeError("queue down")):
			webhooks.on_student_insert(frappe._dict(doctype="Student", name="STU-ERR", school_class=None))
		self.assertTrue(frappe.db.exists("Error Log", {"reference_name": "STU-ERR"}))

	# ------------------------------------------------------------------ configuration and permissions
	def test_endpoint_validation(self):
		with self.assertRaises(frappe.ValidationError):
			self.endpoint(events="student.created\npayroll.run")
		with self.assertRaises(frappe.ValidationError), patch.object(webhooks, "_lookup", return_value=["10.0.0.7"]):
			frappe.get_doc({"doctype": webhooks.ENDPOINT, "endpoint_url": "https://intranet.example.test/h",
							"enabled": 1, "event_types": "student.created", "secret": "s"}).insert()

	def test_deliveries_are_read_only_and_the_secret_is_never_returned(self):
		endpoint = self.endpoint()
		email = f"hooks-{frappe.generate_hash(length=5)}@webhooks.test"
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Hooks", "send_welcome_email": 0,
						"roles": [{"role": "School Admin"}]}).insert(ignore_permissions=True)
		self.assertTrue(frappe.has_permission(webhooks.ENDPOINT, "write", user=email))
		self.assertTrue(frappe.has_permission(webhooks.DELIVERY, "read", user=email))
		for ptype in ("create", "write", "delete"):
			self.assertFalse(frappe.has_permission(webhooks.DELIVERY, ptype, user=email), ptype)
		frappe.set_user(email)
		self.assertNotEqual(frappe.client.get(webhooks.ENDPOINT, endpoint.name)["secret"], "receiver-secret")
