"""Configurable SMS gateways against a real local HTTPS receiver: request formats, credentials, success rules, failures
that arrive as HTTP 200, safety of the destination, and the School Settings path.
bench --site <site> run-tests --module school_erp.tests.test_sms_gateway"""

import datetime
import http.server
import json
import os
import ssl
import tempfile
import threading
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import frappe

from school_erp.api import messaging, sms_gateway
from school_erp.tests.test_integration import TestCase, setup_school

HOST = "sms.example.test"
PUBLIC = "93.184.216.34"
API_KEY = "sk-live-0123456789abcdef"


def _certificate(directory):
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
		f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
	return paths


class _Provider(http.server.BaseHTTPRequestHandler):
	"""Records each request and answers with whatever the test set (status, body)."""

	def _handle(self):
		length = int(self.headers.get("Content-Length") or 0)
		body = self.rfile.read(length).decode() if length else ""
		self.server.received.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
		status, reply = self.server.reply
		self.send_response(status)
		self.end_headers()
		self.wfile.write(reply.encode())

	do_GET = do_POST = _handle

	def log_message(self, *args):
		pass


class TestSMSGateway(TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		setup_school(cls)
		cls._dir = tempfile.TemporaryDirectory()
		cls.cert, key = _certificate(cls._dir.name)
		context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
		context.load_cert_chain(cls.cert, key)
		cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
		cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
		cls.server.handle_error = lambda *args: None
		cls.server.received = []
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
		self.server.reply = (200, json.dumps({"responses": [{"response-code": 200, "messageid": "1"}]}))
		self._patches = [patch.object(sms_gateway, "PORT", self.server.server_address[1]),
						 patch.object(sms_gateway, "_ca_bundle", return_value=self.cert)]
		for p in self._patches:
			p.start()

	def tearDown(self):
		for p in self._patches:
			p.stop()
		frappe.db.rollback()

	def gateway(self, **kw):
		values = {"doctype": "School SMS Gateway", "gateway_name": "GW " + frappe.generate_hash(length=6),
				  "url": f"https://{HOST}/api/services/sendsms/?v=2", "http_method": "POST", "body_format": "JSON",
				  "recipient_param": "mobile", "message_param": "message", "sender_param": "shortcode", "sender_id": "STEMIC",
				  "api_key_param": "apikey", "api_key_in": "Body", "api_key": API_KEY,
				  "parameters": [{"parameter": "partnerID", "value": "4321"}],
				  "success_field": "responses.0.response-code", "success_values": "200", **kw}
		with patch.object(sms_gateway, "_lookup", return_value=[PUBLIC]):
			return frappe.get_doc(values).insert()

	def send(self, gw, numbers, message="Hello"):
		with patch.object(sms_gateway, "_lookup", return_value=["127.0.0.1"]) as lookup, \
				patch.object(sms_gateway, "_is_public", return_value=True):
			result = sms_gateway.send(gw.name, numbers, message)
		return result, lookup

	# ------------------------------------------------------------------ formats and credentials
	def test_json_post_one_request_per_number(self):
		gw = self.gateway()
		result, lookup = self.send(gw, ["254712345678", "254722000111"], "Fees due")
		self.assertEqual((result["sent"], result["failed"]), (["254712345678", "254722000111"], []))
		self.assertEqual(lookup.call_count, 2)  # one DNS answer per request, nothing re-resolves it
		first = self.server.received[0]
		self.assertEqual((first["method"], first["path"], first["headers"]["Host"]), ("POST", "/api/services/sendsms/?v=2", HOST))
		self.assertEqual(json.loads(first["body"]), {"mobile": "254712345678", "message": "Fees due", "apikey": API_KEY,
													 "shortcode": "STEMIC", "partnerID": "4321"})

	def test_form_post_all_numbers_with_a_header_key(self):
		gw = self.gateway(body_format="Form", recipients_mode="All numbers in one request", number_format="+2547XXXXXXXX",
						  api_key_param="Authorization", api_key_in="Header", api_key_prefix="Bearer ",
						  parameters=[{"parameter": "X-Partner", "value": "p-1", "is_header": 1}])
		result, _ = self.send(gw, ["254712345678", "254722000111"])
		self.assertEqual(len(result["sent"]), 2)
		[request] = self.server.received
		self.assertEqual(request["headers"]["Authorization"], f"Bearer {API_KEY}")
		self.assertEqual(request["headers"]["X-Partner"], "p-1")
		form = parse_qs(request["body"])
		self.assertEqual(form["mobile"], ["+254712345678,+254722000111"])
		self.assertNotIn("Authorization", form)

	def test_get_with_local_numbers_and_a_text_rule(self):
		self.server.reply = (200, "1701|Sent OK")
		gw = self.gateway(http_method="GET", number_format="07XXXXXXXX", success_field="", success_values="",
						  success_text="Sent OK")
		result, _ = self.send(gw, ["254712345678"])
		self.assertEqual(result["sent"], ["254712345678"])
		query = parse_qs(urlsplit(self.server.received[0]["path"]).query)
		self.assertEqual((query["mobile"], query["v"], query["apikey"]), (["0712345678"], ["2"], [API_KEY]))

	# ------------------------------------------------------------------ failures
	def test_a_200_reply_with_an_error_inside_is_a_failure(self):
		self.server.reply = (200, json.dumps({"responses": [{"response-code": 1004, "response-description": "Low bulk credits"}]}))
		gw = self.gateway()
		result, _ = self.send(gw, ["254712345678"])
		self.assertEqual((result["sent"], result["failed"]), ([], ["254712345678"]))
		self.assertIn("1004", result["errors"][0])
		log = frappe.get_last_doc("Error Log", filters={"method": ("like", f"%{gw.name}%")})
		self.assertIn("Low bulk credits", log.error)
		self.assertNotIn(API_KEY, log.error)

	def test_http_errors_and_unreadable_replies_fail(self):
		gw = self.gateway()
		self.server.reply = (500, "upstream down")
		self.assertEqual(self.send(gw, ["254712345678"])[0]["failed"], ["254712345678"])
		self.server.reply = (200, "<html>maintenance</html>")
		result = self.send(gw, ["254712345678"])[0]
		self.assertEqual(result["failed"], ["254712345678"])
		self.assertIn("not JSON", result["errors"][0])

	def test_the_api_key_never_appears_in_errors(self):
		self.server.reply = (401, f"invalid key {API_KEY}")
		result = self.send(self.gateway(), ["254712345678"])[0]
		self.assertNotIn(API_KEY, result["errors"][0])
		self.assertIn("***", result["errors"][0])

	# ------------------------------------------------------------------ destination safety
	def test_unsafe_urls_are_refused_on_save(self):
		for url in ("http://sms.example.test/send", "https://localhost/send", "https://sms.example.test:8443/send",
					"https://user:pw@sms.example.test/send"):
			with self.subTest(url=url), self.assertRaises(frappe.ValidationError):
				self.gateway(url=url)
		with patch.object(sms_gateway, "_lookup", return_value=["10.0.0.5"]), self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "School SMS Gateway", "gateway_name": "Internal", "url": "https://intranet.example.test/s",
							"recipient_param": "to", "message_param": "text"}).insert()

	def test_a_name_that_now_points_inside_is_refused_before_connecting(self):
		gw = self.gateway()  # public when saved
		with patch.object(sms_gateway, "_lookup", return_value=["127.0.0.1"]):
			result = sms_gateway.send(gw.name, ["254712345678"], "Hello")
		self.assertEqual(result["failed"], ["254712345678"])
		self.assertIn("not a public", result["errors"][0])
		self.assertEqual(self.server.received, [])

	def test_a_success_field_needs_its_values(self):
		with self.assertRaises(frappe.ValidationError):
			self.gateway(success_values="")

	# ------------------------------------------------------------------ the school's path
	def test_school_settings_route_messages_through_the_gateway(self):
		gw = self.gateway()
		with patch.object(frappe, "get_cached_doc", side_effect=self._settings_with(gw.name)):
			result, _ = self._via_messaging(["0712 345 678"])
		self.assertEqual(result, {"sent": ["254712345678"], "failed": []})
		self.assertTrue(frappe.db.exists("SMS Log", {"sent_to": "254712345678", "message": "Term fees are due"}))

	def _settings_with(self, gateway):
		real = frappe.get_cached_doc

		def get(doctype, *args, **kwargs):
			doc = real(doctype, *args, **kwargs)
			if doctype == "School Settings":
				doc = frappe.get_doc(doc.as_dict())
				doc.sms_provider, doc.sms_gateway, doc.country_code = "SMS Gateway", gateway, "254"
			return doc

		return get

	def _via_messaging(self, numbers):
		with patch.object(sms_gateway, "_lookup", return_value=["127.0.0.1"]) as lookup, \
				patch.object(sms_gateway, "_is_public", return_value=True):
			return messaging.send_sms(numbers, "Term fees are due"), lookup

	def test_send_test_reports_what_happened(self):
		gw = self.gateway(test_number="0712345678")
		with patch.object(sms_gateway, "_lookup", return_value=["127.0.0.1"]), \
				patch.object(sms_gateway, "_is_public", return_value=True):
			self.assertEqual(sms_gateway.send_test(gw.name), {"sent": True, "number": "254712345678", "error": ""})
			self.server.reply = (200, json.dumps({"responses": [{"response-code": 1003}]}))
			out = sms_gateway.send_test(gw.name)
		self.assertFalse(out["sent"])
		self.assertIn("1003", out["error"])
