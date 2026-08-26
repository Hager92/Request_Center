app_name = "request_center"
app_title = "Request Center"
app_publisher = "Hager"
app_description = "Create, configure, approve, track, and manage employee requests."
app_email = "Hager@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "request_center",
		"title": "Request Center",
		"route": "/app/request-center-home",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/request_center/css/request_center.css"
app_include_js = "/assets/request_center/js/request_center.js"

# include js, css files in header of web template
# web_include_css = "/assets/request_center/css/request_center.css"
# web_include_js = "/assets/request_center/js/request_center.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "request_center/public/scss/website"

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
# app_include_icons = "request_center/public/icons.svg"

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

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "request_center.utils.jinja_methods",
# 	"filters": "request_center.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "request_center.install.before_install"
# after_install = "request_center.install.after_install"
after_install = [
	"request_center.setup.request_categories.ensure_request_categories",
	"request_center.setup.request_type_config.migrate_approval_levels_onto_request_types",
	"request_center.setup.request_type_config.migrate_request_approval_workflow",
	"request_center.setup.purchase_links.ensure_purchase_document_links",
]
after_migrate = [
	"request_center.setup.request_categories.ensure_request_categories",
	"request_center.setup.request_type_config.migrate_approval_levels_onto_request_types",
	"request_center.setup.request_type_config.migrate_request_approval_workflow",
	"request_center.setup.purchase_links.ensure_purchase_document_links",
]

# Uninstallation
# ------------

# before_uninstall = "request_center.uninstall.before_uninstall"
# after_uninstall = "request_center.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "request_center.utils.before_app_install"
# after_app_install = "request_center.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "request_center.utils.before_app_uninstall"
# after_app_uninstall = "request_center.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "request_center.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "request_center.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Requests": "request_center.permissions.get_request_permission_query_conditions",
}

has_permission = {
	"Requests": "request_center.permissions.has_request_permission",
}

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
		"request_center.request_center.doctype.requests.requests.update_request_list_tracking"
	],
}

# Testing
# -------

# before_tests = "request_center.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "request_center.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "request_center.event.get_events"
# }
override_whitelisted_methods = {
	"frappe.model.workflow.apply_workflow": "request_center.api.requests.apply_workflow"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "request_center.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["request_center.utils.before_request"]
# after_request = ["request_center.utils.after_request"]

# Job Events
# ----------
# before_job = ["request_center.utils.before_job"]
# after_job = ["request_center.utils.after_job"]

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
# 	"request_center.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

fixtures = [
    {
        "doctype": "Workflow",
        "filters": [
            ["name", "=", "Approval Engine"]
        ]
    },
        {
        "doctype": "Workspace",
        "filters": [
            ["name", "=", "Request Center"]
        ]
    },
    {
        "doctype": "Request Category",
        "filters": [
            ["name", "in", [
                "Service Request",
                "Material Request",
                "Disbursement Request",
                "Other Requests"
            ]]
        ]
    }
]