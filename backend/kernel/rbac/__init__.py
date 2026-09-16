"""Role-based access control.

Permissions are declared in code (`permissions.py` in each app) and registered centrally, so the
full set is known without reading the database. Roles, their permissions and their assignments are
per-tenant data, because one pharmacy's idea of "Counter Staff" is not another's.
"""
