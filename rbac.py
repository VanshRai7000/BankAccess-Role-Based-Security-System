"""
RBAC Engine — Core permission logic for the Banking Management System.
Every user action is evaluated against the role-permission mapping defined here.

NOTE: CUSTOMER_WITHDRAW_LIMIT is no longer hardcoded here.
      It is stored in the `settings` table and fetched at runtime via get_setting().
"""

ROLE_PERMISSIONS = {
    'admin':    ['view', 'view_own', 'deposit', 'withdraw', 'approve', 'delete', 'manage_users', 'view_logs', 'manage_settings'],
    'manager':  ['view', 'view_own', 'approve', 'view_logs'],
    'teller':   ['view', 'view_own', 'deposit', 'withdraw'],
    'customer': ['view_own', 'deposit', 'withdraw_limited'],
}

ROLE_LABELS = {
    'admin':    'Administrator',
    'manager':  'Manager',
    'teller':   'Teller',
    'customer': 'Customer',
}


def check_permission(user_role: str, action: str) -> bool:
    """Return True if the role has the given permission."""
    return action in ROLE_PERMISSIONS.get(user_role, [])


def get_permissions(user_role: str) -> list:
    """Return all permissions for a role."""
    return ROLE_PERMISSIONS.get(user_role, [])


def get_role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.capitalize())
