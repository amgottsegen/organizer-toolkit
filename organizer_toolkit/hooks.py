app_name = "organizer_toolkit"
app_title = "Organizer Toolkit"
app_publisher = "CREATE Lab"
app_description = "Tools for organizing constituents"
app_email = "iglesiascrmtech@gmail.com"
app_license = "mit"

fixtures = [
	"Client Script",
	"Number Card",
	{"dt": "OT Language"},
	{"dt": "OT Constituent Type"},
	{"dt": "OT Resident Type"},
	{"dt": "OT Assessment"},
	{"dt": "OT Activity"},
	# Custom DocPerm is deliberately NOT a fixture. Permissions for doctypes this app
	# owns live in their doctype JSON. A Custom DocPerm row shadows the JSON entirely
	# (see frappe/model/meta.py Meta.set_custom_permissions), so exporting them here
	# would re-import the shadowing rows on every migrate and silently override the
	# permissions in source. Editing permissions via the desk UI recreates them --
	# change the doctype JSON and migrate instead.
	{"dt": "Role", "filters": [["Name", "like", "OT%"]]},
	{"dt": "Role Profile", "filters": [["Name", "like", "OT%"]]},
	{"dt": "Global Search Settings"},
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "organizer_toolkit",
# 		"logo": "/assets/organizer_toolkit/logo.png",
# 		"title": "Organizer Toolkit",
# 		"route": "/organizer_toolkit",
# 		"has_permission": "organizer_toolkit.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/organizer_toolkit/css/organizer_toolkit.css"
app_include_js = [
	"/assets/organizer_toolkit/js/map_defaults.js",
	"/assets/organizer_toolkit/js/canvass_quick_entry.js",
]

# Publishes OT Locality Settings to frappe.boot.ot_locality so client-side code can read
# the configured city without a server round trip.
extend_bootinfo = ["organizer_toolkit.boot.boot_session"]

# include js, css files in header of web template
# web_include_css = "/assets/organizer_toolkit/css/organizer_toolkit.css"
# web_include_js = "/assets/organizer_toolkit/js/organizer_toolkit.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "organizer_toolkit/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "organizer_toolkit/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "organizer_toolkit.utils.jinja_methods",
# 	"filters": "organizer_toolkit.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "organizer_toolkit.install.before_install"
# after_install = "organizer_toolkit.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "organizer_toolkit.uninstall.before_uninstall"
# after_uninstall = "organizer_toolkit.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "organizer_toolkit.utils.before_app_install"
# after_app_install = "organizer_toolkit.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "organizer_toolkit.utils.before_app_uninstall"
# after_app_uninstall = "organizer_toolkit.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "organizer_toolkit.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"organizer_toolkit.tasks.report_to_drive.upload_daily_report_to_drive",
		"organizer_toolkit.doorknocking.doorknocking_map.generate_doorknocking_map",
	],
	# Drains the backlog of addresses with no coordinates a batch at a time, paced for
	# Nominatim's one-request-per-second limit. No-ops once everything is geocoded.
	"hourly_long": [
		"organizer_toolkit.tasks.geocode_backfill.run",
	],
}

# scheduler_events = {
# 	"all": [
# 		"organizer_toolkit.tasks.all"
# 	],
# 	"daily": [
# 		"organizer_toolkit.tasks.daily"
# 	],
# 	"hourly": [
# 		"organizer_toolkit.tasks.hourly"
# 	],
# 	"weekly": [
# 		"organizer_toolkit.tasks.weekly"
# 	],
# 	"monthly": [
# 		"organizer_toolkit.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "organizer_toolkit.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "organizer_toolkit.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "organizer_toolkit.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["organizer_toolkit.utils.before_request"]
# after_request = ["organizer_toolkit.utils.after_request"]

# Job Events
# ----------
# before_job = ["organizer_toolkit.utils.before_job"]
# after_job = ["organizer_toolkit.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"organizer_toolkit.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
