import frappe

from organizer_toolkit.locality import get_locality


def boot_session(bootinfo):
	"""Expose locality settings to client scripts.

	Wired via `extend_bootinfo` so static assets like map_defaults.js -- which load
	before any form and cannot call the server -- can read the configured map centre
	and address defaults synchronously from `frappe.boot.ot_locality`.
	"""
	try:
		bootinfo.ot_locality = get_locality()
	except Exception:
		# Never let a settings problem break desk login; the client falls back to its
		# own defaults when this key is absent.
		frappe.log_error(title="Locality boot failed", message=frappe.get_traceback())
