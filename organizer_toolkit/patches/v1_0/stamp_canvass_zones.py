"""Stamp every geocoded address with the zone it falls in, and pass it to the doorknocks.

`OT Address.zone` is derived in before_save, so addresses that already existed carry
nothing until something touches them. Same story on `OT Canvass Attempt.zone`, which
fetches from the address.

Deriving it from coordinates rather than from the walk list is the point: only a minority
of doorknocks are logged against a walk list, so a fetch through that link would leave
most of them unfiltered. The zone is a fact about where the door is.
"""

import frappe

from organizer_toolkit.organizer_toolkit.doctype.ot_canvass_zone.ot_canvass_zone import (
	restamp_addresses,
)


def execute():
	for doctype in ("OT Address", "OT Canvass Attempt", "OT Canvass Zone"):
		if not frappe.db.table_exists(doctype):
			return

	changed = restamp_addresses()
	frappe.db.commit()

	print(f"  stamped a zone onto {changed} address(es) and the doorknocks there")
