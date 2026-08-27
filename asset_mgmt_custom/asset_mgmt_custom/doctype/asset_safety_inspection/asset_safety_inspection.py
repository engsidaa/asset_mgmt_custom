import frappe
from frappe.model.document import Document


class AssetSafetyInspection(Document):
    def validate(self):
        if self.inspection_date and self.next_inspection_date:
            if self.next_inspection_date <= self.inspection_date:
                frappe.throw("Next Inspection Date must be after Inspection Date.")
