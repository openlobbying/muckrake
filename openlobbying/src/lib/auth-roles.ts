export const ADMIN_ROLE = 'admin';

export interface RoleBearingUser {
	role?: string | null;
}

export function getUserRoles(role: string | null | undefined): string[] {
	return String(role ?? '')
		.split(',')
		.map((value) => value.trim().toLowerCase())
		.filter(Boolean);
}

export function isAdminRole(role: string | null | undefined): boolean {
	return getUserRoles(role).includes(ADMIN_ROLE);
}

export function isAdminUser(user: RoleBearingUser | null | undefined): boolean {
	return isAdminRole(user?.role);
}
