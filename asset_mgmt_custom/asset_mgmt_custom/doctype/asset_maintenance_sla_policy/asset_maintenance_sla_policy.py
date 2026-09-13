import frappe
from frappe import _
from frappe.model.document import Document


class AssetMaintenanceSLAPolicy(Document):
	def validate(self):
		self._check_single_it_general_policy()

	def _check_single_it_general_policy(self):
		"""
		is_it_general_policy مفروض يكون علامة على سياسة واحدة بالضبط
		(AssetWorkOrder._apply_sla_policy تبحث عن أول تطابق بلا ترتيب
		محدد) — لو اتفعّلت على أكثر من سياسة، أيهما تُطبَّق فعلياً على
		شكاوى IT العامة يصبح غير محدد (يعتمد على ترتيب الصفوف في قاعدة
		البيانات). نمنع هذا عند الحفظ بدل ترك الأمر مبهماً.
		"""
		if not self.is_it_general_policy:
			return
		other = frappe.db.get_value(
			"Asset Maintenance SLA Policy",
			{"is_it_general_policy": 1, "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(
				_("Policy {0} is already marked as the general IT policy. Only one policy can carry this flag.").format(other),
				title=_("Duplicate IT Policy"),
			)
