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


_patch_restaurant_pro_arabic_workspace_referer()
