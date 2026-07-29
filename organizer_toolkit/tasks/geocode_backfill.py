"""Work through addresses that have no coordinates yet.

Most addresses arrived from the constituent migration with nothing but a street and a
city, so roughly half the doors on the map would be missing without this. Nominatim
allows one request per second, so the job takes a capped batch, paces itself, and exits
when there is nothing left -- it costs nothing on the hours after the backlog drains.
"""

import time

import frappe

from organizer_toolkit.organizer_toolkit.doctype.ot_address.ot_address import geocode

# Kept small so an hourly run stays well inside Nominatim's fair-use expectations.
BATCH_SIZE = 60
SECONDS_BETWEEN_REQUESTS = 1.1


def pending_count():
	"""Addresses still missing coordinates.

	`["is", "not set"]` rather than a comparison against "" or None: Frappe turns this
	into `ifnull(location, '') = ''`, which is the only form that catches both. The
	column is NULL for every address that has never been geocoded.
	"""
	return frappe.db.count("OT Address", {"location": ["is", "not set"]})


def run(batch_size=BATCH_SIZE, pace=SECONDS_BETWEEN_REQUESTS):
	"""Geocode a batch of addresses that have no location. Safe to run repeatedly."""
	if not frappe.db.table_exists("OT Address"):
		return

	addresses = frappe.get_all(
		"OT Address",
		filters={"location": ["is", "not set"]},
		# Oldest first, so the migrated backlog drains before newer additions.
		order_by="creation asc",
		limit_page_length=batch_size,
		pluck="name",
	)

	if not addresses:
		return

	succeeded = 0

	for index, name in enumerate(addresses):
		if index:
			# Rate limit, not politeness: Nominatim blocks clients that exceed 1/sec.
			time.sleep(pace)

		try:
			if geocode(frappe.get_doc("OT Address", name)):
				succeeded += 1
				frappe.db.commit()
		except Exception:
			# One unresolvable address must not abandon the rest of the batch.
			frappe.db.rollback()
			frappe.log_error(
				title="Geocode backfill failed for an address",
				message=f"{name}\n\n{frappe.get_traceback()}",
			)

	remaining = pending_count()
	print(f"  geocoded {succeeded} of {len(addresses)} attempted; {remaining} address(es) still pending")

	return {"attempted": len(addresses), "succeeded": succeeded, "remaining": remaining}
