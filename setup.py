from setuptools import setup, find_packages

setup(
    name="asset_mgmt_custom",
    version="0.0.1",
    description="Custom extensions for ERPNext Asset & Maintenance modules",
    author="Custom",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe", "erpnext"],
)
