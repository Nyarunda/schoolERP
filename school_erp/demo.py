"""Demo data for presentations and for trying the dashboards.

    bench --site demo.localhost execute school_erp.demo.make_demo

Only runs on a site with developer_mode on and fewer than 5 students, so it can never touch a real school.
Creates classes' streams, ~70 students with guardians, fees, a term's billing and 30 days of payments,
staff (teachers, drivers), a timetable, duty roster, leave, notices, complaints, discipline, expenses
and today's driver check-ins. Demo logins: head@demo.school / teacher@demo.school (password: Demo@2026).
"""

import random

import frappe
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

FIRST = ["Amani", "Baraka", "Wanjiru", "Achieng", "Kipchoge", "Njeri", "Otieno", "Mwangi", "Chebet", "Kamau", "Atieno",
		 "Wafula", "Nyambura", "Ouma", "Jepkosgei", "Mutua", "Akinyi", "Kiprono", "Wairimu", "Odhiambo", "Zawadi", "Imani"]
LAST = ["Kamau", "Otieno", "Mwangi", "Wanjiku", "Kiptoo", "Ochieng", "Njoroge", "Mutai", "Omondi", "Kariuki", "Were", "Cheruiyot"]
PASSWORD = "Demo@2026"


def _user(email, first, roles):
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "send_welcome_email": 0})
		u.insert(ignore_permissions=True)
	from frappe.utils.password import update_password

	update_password(email, PASSWORD)
	frappe.get_doc("User", email).add_roles(*roles)
	return email


def make_demo(force=False):
	if not frappe.conf.developer_mode and not force:
		frappe.throw("Demo data only runs with developer_mode on")
	if frappe.db.count("Student") >= 5 and not force:
		frappe.throw("This site already has students; demo data is only for empty sites")
	random.seed(42)
	frappe.flags.mute_emails = True
	settings = frappe.get_doc("School Settings")
	company = settings.company
	today = getdate(nowdate())

	# accounts for payment modes
	cash = frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0})
	for mop in ("M-Pesa", "Cash"):
		if frappe.db.exists("Mode of Payment", mop):
			doc = frappe.get_doc("Mode of Payment", mop)
			if not any(a.company == company for a in doc.accounts):
				doc.append("accounts", {"company": company, "default_account": cash})
				doc.save(ignore_permissions=True)

	from school_erp.school.doctype.school_term.school_term import get_current_term

	term = get_current_term(today)
	if not term:
		frappe.throw("Run School Setup first (no terms)")

	# --------------------------------------------------------------- staff
	head = _user("head@demo.school", "Grace", ["Head Teacher", "School Admin", "Bursar"])
	tuser = _user("teacher@demo.school", "Peter", ["Teacher", "Staff"])
	settings.reload()
	settings.head_teacher_user = head
	settings.transport_manager_user = head
	settings.save(ignore_permissions=True)

	def staff(name, stype, gender, designation, user=None):
		existing = frappe.db.get_value("Staff Member", {"full_name": name})
		if existing:
			return existing
		return frappe.get_doc({"doctype": "Staff Member", "full_name": name, "staff_type": stype, "gender": gender,
							   "designation": designation, "phone": f"07{random.randint(10000000, 99999999)}", "user": user}).insert().name

	head_staff = staff("Grace Wambui", "Administration", "Female", "Principal", head)
	peter = staff("Peter Otieno", "Teaching", "Male", "Class Teacher", tuser)
	teachers = [peter] + [staff(n, "Teaching", g, "Teacher") for n, g in [
		("Mary Achieng", "Female"), ("John Kamau", "Male"), ("Esther Njeri", "Female"), ("David Kiptoo", "Male"),
		("Lucy Wanjiru", "Female"), ("Samuel Ouma", "Male"), ("Ruth Chebet", "Female")]]
	drivers = [staff(n, "Driver", "Male", "Driver") for n in ("Joseph Mutua", "Francis Were", "Tom Ochieng")]
	staff("Alice Muthoni", "Support", "Female", "Cook")
	for t in teachers:
		frappe.db.set_value("Staff Member", t, "reports_to", head_staff)

	# --------------------------------------------------------------- streams, vehicles, routes, activities
	classes = frappe.get_all("School Class", filters={"is_active": 1}, order_by="level", pluck="name")[2:8] or \
		frappe.get_all("School Class", order_by="level", pluck="name")[:6]
	streams = []
	for i, cls in enumerate(classes):
		for sname in ("East", "West"):
			n = f"{cls} {sname}"
			if not frappe.db.exists("Stream", n):
				tch = frappe.db.get_value("Staff Member", teachers[(i * 2 + (sname == "West")) % len(teachers)], "teacher")
				frappe.get_doc({"doctype": "Stream", "school_class": cls, "stream_name": sname, "class_teacher": tch}).insert()
			streams.append(n)
	vehicles = []
	for reg, drv in zip(("KDA 101A", "KDB 202B", "KDC 303C"), drivers):
		if not frappe.db.exists("School Vehicle", reg):
			frappe.get_doc({"doctype": "School Vehicle", "registration_number": reg, "make_model": "Isuzu NQR 33-seater",
							"capacity": 33, "default_driver": drv, "insurance_expiry": add_days(today, 200 if reg != "KDC 303C" else 9),
							"inspection_expiry": add_days(today, 120)}).insert()
		vehicles.append(reg)
	routes = []
	for (rname, fee), veh, drv in zip((("Ngong Road", 9000), ("Thika Road", 10500), ("Langata", 8000)), vehicles, drivers):
		if not frappe.db.exists("Transport Route", rname):
			frappe.get_doc({"doctype": "Transport Route", "route_name": rname, "fee_per_term": fee, "fee_type": "Transport",
							"vehicle": veh, "driver": drv, "stops": "Stage 1\nStage 2\nStage 3"}).insert()
		routes.append(rname)
	for act, fee in (("Swimming", 3500), ("Football", 1500), ("Music", 2500)):
		if not frappe.db.exists("School Activity", act):
			frappe.get_doc({"doctype": "School Activity", "activity_name": act, "fee_per_term": fee, "fee_type": "Games & Activities"}).insert()

	# --------------------------------------------------------------- fee structures
	if not frappe.db.exists("School Fee Structure", {"school_term": term.name, "school_class": ("is", "not set")}):
		frappe.get_doc({"doctype": "School Fee Structure", "school_term": term.name, "boarding_type": "All",
						"items": [{"fee_type": "Tuition", "amount": 18000}, {"fee_type": "Lunch", "amount": 6500},
								  {"fee_type": "Exam Fee", "amount": 1200}]}).insert()
	for i, cls in enumerate(classes):
		if not frappe.db.exists("School Fee Structure", {"school_term": term.name, "school_class": cls}):
			frappe.get_doc({"doctype": "School Fee Structure", "school_term": term.name, "school_class": cls, "boarding_type": "All",
							"items": [{"fee_type": "Tuition", "amount": 18000 + i * 1500}]}).insert()

	# --------------------------------------------------------------- students + billing + payments
	from school_erp.api.billing import bill_single_student

	students = []
	for i in range(72):
		stream = streams[i % len(streams)]
		first, last = random.choice(FIRST), random.choice(LAST)
		s = frappe.get_doc({
			"doctype": "Student", "first_name": first, "last_name": last, "stream": stream,
			"gender": random.choice(["Female", "Male"]), "boarding_type": "Boarder" if i % 9 == 0 else "Day",
			"admission_date": add_days(term.start_date, -random.randint(0, 900)) if i % 12 else add_days(term.start_date, 3),
			"takes_lunch": int(i % 3 != 0), "transport_route": routes[i % 3] if i % 2 == 0 else None,
			"activities": [{"activity": random.choice(["Swimming", "Football", "Music"])}] if i % 4 == 0 else [],
			"guardians": [{"guardian_name": f"{random.choice(FIRST)} {last}", "relation": random.choice(["Mother", "Father"]),
						   "mobile_no": f"07{random.randint(10000000, 99999999)}", "is_primary": 1}],
		}).insert()
		students.append(s.name)
		bill_single_student(s.name, term.name, posting_date=term.start_date, due_date=add_days(term.start_date, 14))

	mops = ["M-Pesa"] * 4 + ["Cash"]
	for idx, s in enumerate(students):
		bal = flt(frappe.db.get_value("Sales Invoice", {"student": s, "docstatus": 1}, "outstanding_amount"))
		if idx % 7 == 6 or not bal:
			continue  # some never pay
		parts = random.choice([1, 2, 3])
		share = random.choice([1.0, 1.0, 0.85, 0.6, 0.4])
		for p in range(parts):
			amount = round(bal * share / parts, -2)
			if amount <= 0:
				continue
			fp = frappe.get_doc({"doctype": "Fee Payment", "student": s, "amount": amount,
								 "posting_date": add_days(today, -random.randint(0, 29)), "mode_of_payment": random.choice(mops),
								 "reference_no": "Q" + frappe.generate_hash(length=9).upper(), "payer_name": "Parent"})
			fp.insert()
			fp.submit()

	# paybill transactions incl. one unmatched
	from school_erp.api.paybill import record_confirmation

	for ref, amt in ((students[1].lower().replace("-", ""), 2500), ("ADM 9999", 4000)):
		record_confirmation({"TransactionType": "Pay Bill", "TransID": "R" + frappe.generate_hash(length=9).upper(),
							 "TransTime": now_datetime().strftime("%Y%m%d%H%M%S"), "TransAmount": str(amt), "BusinessShortCode": "600000",
							 "BillRefNumber": ref, "MSISDN": "2547 ***** 126", "FirstName": "JANE", "LastName": "PARENT"}, source="Test")

	# --------------------------------------------------------------- timetable for Peter (today's lessons)
	pt = frappe.db.get_value("Staff Member", peter, "teacher")
	periods = frappe.get_all("Period", filters={"is_break": 0}, order_by="sequence", pluck="name")
	subjects = frappe.get_all("Subject", pluck="name")
	day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][today.weekday()]
	day = day if day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday") else "Monday"
	for k, stream in enumerate(streams[:3]):
		name = f"{stream} - {term.name}"
		if frappe.db.exists("Timetable", name) or not periods:
			continue
		slots = []
		for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
			for j, p in enumerate(periods):
				mine = (j + k) % 3 == 0
				other = frappe.db.get_value("Staff Member", teachers[1 + (j + k) % (len(teachers) - 1)], "teacher")
				slots.append({"day": d, "period": p, "subject": subjects[(j + k) % len(subjects)] if subjects else None,
							  "teacher": pt if mine else other, "room": f"Room {k + 1}"})
		# teachers are rotated per stream so nobody is double-booked
		frappe.get_doc({"doctype": "Timetable", "stream": stream, "school_term": term.name, "slots": slots}).insert()

	# --------------------------------------------------------------- duty, leave, notices
	if not frappe.db.exists("Duty Roster", {"from_date": ("<=", today), "to_date": (">=", today)}):
		frappe.get_doc({"doctype": "Duty Roster", "from_date": add_days(today, -today.weekday()), "to_date": add_days(today, 6 - today.weekday()),
						"members": [{"staff_member": peter, "duty_role": "Teacher on Duty"},
									{"staff_member": teachers[2], "duty_role": "Deputy on Duty"}]}).insert()
	from school_erp.api.staff import decide_leave

	for who, reliever, ltype, start, days in ((teachers[3], teachers[1], "Sick Leave", today, 2),
											  (teachers[5], peter, "Compassionate Leave", today, 3),
											  (drivers[2], None, "Annual Leave", add_days(today, 10), 2)):
		la = frappe.get_doc({"doctype": "Leave Application", "staff_member": who, "leave_type": ltype, "from_date": start,
							 "to_date": add_days(start, days - 1), "reason": "Demo", "reliever": reliever,
							 "attachment": "/files/doctor-note.pdf" if ltype == "Sick Leave" else None})
		try:
			la.insert()
			if start == today:
				decide_leave(la.name, "Approved")
		except frappe.ValidationError:
			pass
	frappe.get_doc({"doctype": "Leave Application", "staff_member": teachers[6], "leave_type": "Annual Leave",
					"from_date": add_days(today, 20), "to_date": add_days(today, 22), "reason": "Wedding", "reliever": teachers[4]}).insert()

	for title, aud, prio, msg, pin in (
		("Staff meeting on Friday at 3:30 pm", "All Staff", "Important", "All staff to attend in the staff room. Agenda: end-of-term exams and report forms.", 1),
		("Exam timetable is out", "Teaching Staff", "Normal", "End-of-term exams start on Monday. Collect invigilation schedules from the Deputy.", 0),
		("Fire drill tomorrow 10:00", "All Staff", "Urgent", "Guide your class to the assembly point when the bell rings three times.", 0),
		("Fuel cards renewed", "Drivers", "Normal", "Collect your new fuel card from the bursar's office.", 0)):
		frappe.get_doc({"doctype": "School Notice", "title": title, "audience": aud, "priority": prio, "message": msg, "pinned": pin}).insert()

	# --------------------------------------------------------------- welfare
	for cat, sev, act in (("Lateness", "Minor", "Verbal Warning"), ("Fighting", "Major", "Parent Summoned"), ("Uniform / Grooming", "Minor", "Verbal Warning"),
						  ("Bullying", "Major", "Counselling"), ("Lateness", "Minor", "Detention"), ("Phone / Gadgets", "Minor", "Written Warning"),
						  ("Lateness", "Minor", "None yet"), ("Disrespect", "Minor", "Counselling")):
		frappe.get_doc({"doctype": "Discipline Incident", "student": random.choice(students), "category": cat, "severity": sev,
						"action_taken": act, "incident_date": add_days(today, -random.randint(0, 40)), "description": "Demo incident"}).insert()
	for subj, cat, prio, status in (("Bus arrived late twice", "Transport", "High", "Open"), ("Lunch portions too small", "Meals", "Medium", "In Progress"),
									("Fee statement query", "Fees & Payments", "Low", "Resolved"), ("Child bullied at break", "Bullying", "Urgent", "Open")):
		c = frappe.get_doc({"doctype": "Complaint", "complainant_name": "Demo Parent", "phone": "0711000222", "category": cat,
							"subject": subj, "description": subj, "priority": prio, "source": "Phone"}).insert()
		if status != "Open":
			c.status = status
			c.resolution = "Handled by the office" if status == "Resolved" else None
			c.save()

	# --------------------------------------------------------------- expenses
	from school_erp.api.expenses import decide, request_approval

	cats = frappe.get_all("Expense Category", pluck="name")
	for amt, payee, desc, stage in ((8500, "Total Energies", "Diesel for buses", "approved"), (45000, "Fundi Ltd", "Classroom roof repair", "first"),
									 (3200, "Text Book Centre", "Chalk and markers", "approved"), (12000, "KPLC", "Electricity", "pending"),
									 (2500, "Mama Mboga", "Vegetables", "approved")):
		e = frappe.get_doc({"doctype": "School Expense", "expense_category": random.choice(cats), "amount": amt, "payee": payee,
							"mode_of_payment": "Cash", "description": desc, "posting_date": add_days(today, -random.randint(0, 20))}).insert()
		if stage != "draft":
			request_approval(e.name)
		if stage in ("approved", "first"):
			decide(e.name, "Approved")
			if stage == "approved" and frappe.db.get_value("School Expense", e.name, "status") != "Approved":
				decide(e.name, "Approved")

	# --------------------------------------------------------------- today's driver check-ins (one with issues, one missing)
	for drv, veh, rt, bad in ((drivers[0], vehicles[0], routes[0], False), (drivers[1], vehicles[1], routes[1], True)):
		if frappe.db.exists("Driver Daily Log", {"driver": drv, "log_date": today}):
			continue
		log = frappe.get_doc({"doctype": "Driver Daily Log", "driver": drv, "vehicle": veh, "route": rt,
							  "odometer_start": random.randint(40000, 90000), "fuel_level": "3/4", "fit_to_drive": 1})
		log.insert()
		for row in log.checklist:
			row.ok = 1
		if bad:
			log.checklist[0].ok = 0
			log.checklist[0].remarks = "Rear left tyre worn"
		log.save()
		log.submit()

	frappe.db.commit()
	make_demo_extras(students)
	return f"Demo ready: {len(students)} students. Logins: head@demo.school / teacher@demo.school / parent 0711222333, password {PASSWORD}"


def make_demo_extras(students=None):
	"""Exam results (published report cards), a parent portal login and parent notices."""
	random.seed(7)
	from school_erp.api.exams import generate_report_cards, install_default_scales, publish
	from school_erp.school.doctype.school_term.school_term import get_current_term

	term = get_current_term(getdate(nowdate()))
	install_default_scales()
	students = students or frappe.get_all("Student", filters={"status": "Active"}, pluck="name")
	classes = sorted({frappe.db.get_value("Student", s, "school_class") for s in students})
	subjects = frappe.get_all("Subject", pluck="name", order_by="subject_name")[:6]
	scale = frappe.db.get_single_value("School Settings", "default_grading_scale") or "CBC"
	ename = f"End of {term.term_name} - {term.name}"
	if not frappe.db.exists("Exam", ename):
		exam = frappe.get_doc({"doctype": "Exam", "exam_name": f"End of {term.term_name}", "school_term": term.name, "exam_type": "End-Term",
							   "grading_scale": scale, "max_marks": 100, "classes": [{"school_class": c} for c in classes],
							   "subjects": [{"subject": s} for s in subjects]}).insert()
		ability = {s: random.uniform(35, 92) for s in students}
		for stream in frappe.get_all("Stream", filters={"school_class": ("in", classes)}, pluck="name"):
			for sub in subjects:
				ms = frappe.get_doc({"doctype": "Exam Mark Sheet", "exam": exam.name, "stream": stream, "subject": sub})
				ms.get_students()
				if not ms.marks:
					continue
				for m in ms.marks:
					if random.random() < 0.02:
						m.absent = 1
					else:
						m.marks = str(int(max(5, min(100, random.gauss(ability.get(m.student, 60), 9)))))
				ms.insert()
				_approve_marks(ms)
		generate_report_cards(exam.name)
		publish(exam.name, notify_parents=0)

	_demo_attendance()

	# a parent login for the first student's guardian, plus a sibling so the portal shows two children
	first = frappe.get_doc("Student", students[0])
	sibling = frappe.get_doc("Student", students[13])
	for stu in (first, sibling):
		g = stu.guardians[0]
		g.guardian_name, g.mobile_no, g.email = "Jane Wanjiru", "0711222333", "parent@demo.school"
		stu.save()
	from school_erp.api.portal import give_portal_access

	give_portal_access(student=first.name, send_sms=0)
	give_portal_access(student=sibling.name, send_sms=0)
	from frappe.utils.password import update_password

	update_password("parent@demo.school", PASSWORD)
	frappe.db.set_single_value("System Settings", "allow_login_using_mobile_number", 1)
	s = frappe.get_doc("School Settings")
	s.update({"mpesa_enabled": 1, "mpesa_stk_enabled": 1, "mpesa_shortcode": "174379", "mpesa_environment": "Sandbox"})
	s.save()
	for title, prio, msg in (("Half-term break: Thursday to Sunday", "Important", "School closes Thursday at 12:30 pm and reopens Monday at 7:30 am."),
							 ("Sports day this Friday", "Normal", "Parents are welcome from 10:00. Students should come in their house T-shirts.")):
		if not frappe.db.exists("School Notice", {"title": title}):
			frappe.get_doc({"doctype": "School Notice", "title": title, "audience": "Parents", "priority": prio, "message": msg,
							"pinned": int(prio == "Important")}).insert()
	frappe.db.commit()


def _approve_marks(ms):
	"""Demo marks go through the same approval as real ones (sent, then approved by the Head Teacher)."""
	from frappe.model.workflow import apply_workflow

	from school_erp.school.doctype.exam_mark_sheet.exam_mark_sheet import approval_required

	if not approval_required():
		return ms.submit()
	ms = apply_workflow(ms, "Send for Approval")
	apply_workflow(ms, "Approve")


def _demo_attendance(days=10):
	"""Two weeks of class registers: most children present, a few absent or late."""
	from frappe.utils import add_days

	from school_erp.api.attendance import stream_students

	today = getdate(nowdate())
	for stream in frappe.get_all("Stream", filters={"is_active": 1}, pluck="name"):
		students = stream_students(stream)
		if not students:
			continue
		day, made = today, 0
		while made < days:
			day = add_days(day, -1)
			if day.weekday() >= 5:
				continue
			made += 1
			if frappe.db.exists("Class Attendance", {"stream": stream, "attendance_date": day}):
				continue
			rows = []
			for st in students:
				r = random.random()
				rows.append({"student": st.name, "status": "Absent" if r < 0.04 else "Late" if r < 0.07 else "Excused" if r < 0.08 else "Present"})
			frappe.get_doc({"doctype": "Class Attendance", "stream": stream, "attendance_date": day, "students": rows}).insert()
