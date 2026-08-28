import frappe
from frappe.model.document import Document


class AssetDisposalCertificate(Document):
    def on_submit(self):
        cert_num = f"DCERT-{self.asset}-{self.disposal_date}"
        self.db_set("certificate_number", cert_num)
