__version__ = "0.0.1"


def _patch_restaurant_pro_arabic_workspace_referer():
	"""Runtime compatibility patch (NOT a file edit) for a bug in the
	third-party `restaurant_pro` app's `get_desktop_page` override.

	restaurant_pro/restaurant_pro/overrides/workspace_api.py works around a
	Frappe v15.69 quirk where the desk JS sometimes omits the `page`
	argument, by recovering the workspace name from the HTTP Referer header.
	Its `_page_from_referer()` helper reads `urlparse(referer).path`
	directly, but browsers percent-encode non-ASCII characters in the
	Referer header (RFC 7230 requires header values to be ASCII), so any
	Arabic (or other non-ASCII) workspace name in the URL arrives as e.g.
	`%D8%A5%D8%AF...` and never matches a real workspace name. That
	surfaces to users as:
	"لا يمكن فتح الصفحة: اسم مساحة العمل غير متوفر ..."

	We don't own restaurant_pro and it receives its own updates, so editing
	its file on disk would be silently reverted on the next update. Instead
	this patches the buggy function in memory at process startup, adding a
	`urllib.parse.unquote()` call. If restaurant_pro ever fixes this
	upstream (their source already contains "unquote"), we detect that and
	skip patching so we don't shadow their improved implementation.
	"""
	try:
		import importlib

		rp_workspace_api = importlib.import_module(
			"restaurant_pro.restaurant_pro.overrides.workspace_api"
		)
	except Exception:
		# restaurant_pro not installed on this site, or its module path
		# changed — nothing to patch.
		return

	if not hasattr(rp_workspace_api, "_page_from_referer") or not hasattr(
		rp_workspace_api, "_resolve_workspace_slug"
	):
		return

	try:
		import inspect

		existing_source = inspect.getsource(rp_workspace_api._page_from_referer)
		if "unquote" in existing_source:
			# Already fixed upstream — don't shadow their version.
			return
	except Exception:
		pass

	def _fixed_page_from_referer():
		import frappe
		from urllib.parse import unquote, urlparse

		try:
			referer = getattr(frappe.request, "referrer", None) or ""
			if not referer:
				return None

			parsed = urlparse(referer)
			candidate = unquote(parsed.fragment or parsed.path)

			for prefix in ("/app/", "/"):
				if candidate.startswith(prefix):
					candidate = candidate[len(prefix) :]
					break

			parts = [p for p in candidate.split("/") if p]
			if len(parts) >= 2 and parts[0].lower() in ("workspaces", "workspace"):
				candidate = parts[1]
			elif parts:
				candidate = parts[0]
			else:
				return None

			return rp_workspace_api._resolve_workspace_slug(candidate)
		except Exception:
			return None

	rp_workspace_api._page_from_referer = _fixed_page_from_referer

	try:
		import frappe

		frappe.logger().info(
			"asset_mgmt_custom: patched restaurant_pro._page_from_referer "
			"(percent-decoding fix for non-ASCII workspace names)"
		)
	except Exception:
		pass


def _patch_asset_repair_capitalization_without_purchase_invoice():
	"""Runtime compatibility patch (NOT a file edit) for a real crash in
	ERPNext core's own Asset Repair controller.

	erpnext/assets/doctype/asset_repair/asset_repair.py's
	get_gl_entries_for_repair_cost() does, unconditionally whenever
	repair_cost > 0:

	    frappe.get_doc("Purchase Invoice", self.purchase_invoice).items[0]...

	purchase_invoice is an optional field (no `reqd`, no validation
	requiring it whenever capitalize_repair_cost is checked) — so
	submitting any capitalized (CapEx) Asset Repair with a repair_cost but
	no linked Purchase Invoice crashes with DoesNotExistError. This is a
	genuine, currently-live defect, independent of our own CapEx/OpEx
	work: any capitalize_repair_cost=1 repair entered without a PI hits it.

	asset_mgmt_custom's own overrides/asset_repair.py posts the correct
	journal entry itself (Debit Asset / Credit the Capital Maintenance WIP
	account) for exactly this no-PI case — see _post_repair_cost_gl_entry.
	This patch just stops ERPNext's own method from crashing first: when
	no purchase_invoice is linked, it skips generating that GL entry
	(deferring entirely to our own), and delegates to the original
	implementation unchanged whenever a Purchase Invoice IS linked.
	"""
	try:
		import erpnext.assets.doctype.asset_repair.asset_repair as core_asset_repair
	except Exception:
		return

	if not hasattr(core_asset_repair, "AssetRepair") or not hasattr(
		core_asset_repair.AssetRepair, "get_gl_entries_for_repair_cost"
	):
		return

	original = core_asset_repair.AssetRepair.get_gl_entries_for_repair_cost

	try:
		import inspect

		source = inspect.getsource(original)
		if "self.purchase_invoice" not in source:
			# Behavior changed upstream in a way we don't recognize —
			# safer to not patch than to guess wrong.
			return
		if "if not self.purchase_invoice" in source:
			# Already guarded upstream — don't shadow their fix.
			return
	except Exception:
		pass

	def _patched_get_gl_entries_for_repair_cost(self, gl_entries, fixed_asset_account):
		if not self.purchase_invoice:
			# No PI to source an expense account from — asset_mgmt_custom's
			# own on_submit hook posts the WIP-account journal entry for
			# this case instead. Nothing to do here.
			return
		return original(self, gl_entries, fixed_asset_account)

	core_asset_repair.AssetRepair.get_gl_entries_for_repair_cost = (
		_patched_get_gl_entries_for_repair_cost
	)

	try:
		import frappe

		frappe.logger().info(
			"asset_mgmt_custom: patched AssetRepair.get_gl_entries_for_repair_cost "
			"(skip crash on capitalized repair with no linked Purchase Invoice)"
		)
	except Exception:
		pass


_patch_restaurant_pro_arabic_workspace_referer()
_patch_asset_repair_capitalization_without_purchase_invoice()
