import frappe
from frappe.model.document import Document


class AssetComponent(Document):
    def before_save(self):
        self._compute_level()

    def _compute_level(self):
        if self.parent_component:
            parent_level = frappe.db.get_value("Asset Component", self.parent_component, "level") or 1
            self.level = int(parent_level) + 1
        else:
            self.level = 1
