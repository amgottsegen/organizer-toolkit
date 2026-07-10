import io

import frappe
from frappe.integrations.doctype.google_drive.google_drive import (
	check_for_folder_in_google_drive,
	get_google_drive_object,
)
from frappe.utils.xlsxutils import make_xlsx


def upload_daily_report_to_drive():
	"""Entry point for the scheduler — enqueues the actual work."""
	frappe.enqueue(
		"organizer_toolkit.tasks.report_to_drive._upload_daily_report_to_drive",
		queue="long",
		timeout=1500,
		job_name="daily_report_drive_upload",
	)


def _upload_daily_report_to_drive():
	"""Generate a Report Builder report as XLSX and upload it to Google Drive.
	Scheduled via hooks.py -> scheduler_events -> daily
	"""
	report_name = "All Constituents Basic Info"
	filters = {}

	# 1. Fetch data the way Report Builder reports are meant to be fetched
	report = frappe.get_doc("Report", report_name)
	columns, data = report.get_data(filters=filters, as_dict=False, limit=None)

	# columns is a list of dicts with "label"; data is a list of lists (as_dict=False)
	xlsx_rows = [[c.get("label") for c in columns]]
	xlsx_rows.extend(data)

	xlsx_file = make_xlsx(xlsx_rows, "Report")

	# 2. Reuse the same OAuth object the backup feature uses
	google_drive, account = get_google_drive_object()
	check_for_folder_in_google_drive()
	account.reload()

	if not account.backup_folder_id:
		frappe.throw(
			"No Google Drive backup folder configured. "
			"Set up Google Drive backups first (Settings > Integrations > Google Drive)."
		)

	# 3. Upload
	from googleapiclient.http import MediaIoBaseUpload

	file_metadata = {
		"name": f"{report_name} - {frappe.utils.today()}.xlsx",
		"parents": [account.backup_folder_id],
	}
	media = MediaIoBaseUpload(
		io.BytesIO(xlsx_file.getvalue()),
		mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		resumable=True,
	)

	google_drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
	frappe.logger().info(f"Uploaded '{report_name}' XLSX to Google Drive")
