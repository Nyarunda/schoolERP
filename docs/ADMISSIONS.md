# Online admissions (`admissions` module)

## The public form

Parents apply at **/admission-application** without logging in. Put the link on the school website or social media, or share it in an SMS.

* They get an SMS with a reference number. If the messaging module is on, they get another SMS when an interview is booked, a place is offered or the application is not successful.
* They can check progress at **/admission-status** with the reference and the phone number they applied with. That page shows only the status, never your notes.
* A member of the public can only fill in the application fields. The status, source, notes and stream are always set by the school.
* One phone number can send a limited number of applications per day (*Admission Settings*, default 3).

Untick *Accepting Online Applications* in **Admission Settings** to close the form. Visitors then see your *Message When Closed*. You can also change the alert role and every SMS text there.

## Working an application

**Admission Application** (also for walk-ins and phone enquiries; set *Source*). Use the **Move to** buttons:

Received → Under Review → Interview Scheduled → Offered → Accepted → Admitted

* **Interview Scheduled** asks for the date and time.
* **Rejected** asks for an internal reason, which the parent never sees.
* A rejected or withdrawn application can go back to Under Review.

**Admit as Student** (on Offered or Accepted applications) asks for the stream. It then:
* creates the Student, with the parent as primary guardian;
* copies the birth certificate and previous school, if your Student form has those fields;
* marks the application Admitted, links it to the student, and SMSes the parent the Student ID.

Clicking it twice never creates a second student.

## Report

**Admissions Pipeline**: applications per class and status for a period, how many are still open, and admitted as a % of decided applications.
