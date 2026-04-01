import { fail } from '@sveltejs/kit';
import { ADMIN_ROLE, isAdminRole } from '$lib/auth-roles';
import { auth } from '$lib/server/auth';
import { requireAdmin } from '$lib/server/admin';
import type { Actions, PageServerLoad } from './$types';

type AdminRole = 'admin' | 'user';

function parseRole(value: FormDataEntryValue | null): AdminRole | null {
	const role = String(value ?? '').trim().toLowerCase();
	if (role === 'admin' || role === 'user') {
		return role;
	}

	return null;
}

export const load: PageServerLoad = async ({ locals, request, url }) => {
	requireAdmin(locals, url);

	const result = await auth.api.listUsers({
		query: {
			limit: 100,
			sortBy: 'createdAt',
			sortDirection: 'desc'
		},
		headers: request.headers
	});

	return {
		users: result.users,
		total: result.total
	};
};

async function getAdminCount(request: Request): Promise<number> {
	const result = await auth.api.listUsers({
		query: {
			limit: 1,
			filterField: 'role',
			filterOperator: 'contains',
			filterValue: ADMIN_ROLE
		},
		headers: request.headers
	});

	return result.total;
}

export const actions: Actions = {
	setRole: async ({ locals, request, url }) => {
		requireAdmin(locals, url);

		const formData = await request.formData();
		const userId = String(formData.get('userId') ?? '').trim();
		const role = parseRole(formData.get('role'));

		if (!userId || !role) {
			return fail(400, {
				error: 'User ID is required and role must be either "admin" or "user".'
			});
		}

		try {
			const user = await auth.api.getUser({
				query: {
					id: userId
				},
				headers: request.headers
			});

			if (!user) {
				return fail(404, {
					error: 'User not found.'
				});
			}

			if (isAdminRole(user.role) && role !== ADMIN_ROLE) {
				const adminCount = await getAdminCount(request);
				if (adminCount <= 1) {
					return fail(400, {
						error: 'You cannot remove the last remaining admin.'
					});
				}
			}

			await auth.api.setRole({
				body: {
					userId,
					role
				},
				headers: request.headers
			});

			return {
				success: `Updated ${userId} to role "${role}".`
			};
		} catch (error) {
			return fail(400, {
				error: error instanceof Error ? error.message : 'Failed to update role.'
			});
		}
	},
	createUser: async ({ locals, request, url }) => {
		requireAdmin(locals, url);

		const formData = await request.formData();
		const name = String(formData.get('name') ?? '').trim();
		const email = String(formData.get('email') ?? '').trim();
		const password = String(formData.get('password') ?? '').trim();
		const role = parseRole(formData.get('role')) ?? 'user';

		if (!name || !email || !password) {
			return fail(400, {
				error: 'Name, email, and password are required to create a user.'
			});
		}

		try {
			const created = await auth.api.createUser({
				body: {
					name,
					email,
					password,
					role
				},
				headers: request.headers
			});

			return {
				success: `Created ${created.user.email}.`
			};
		} catch (error) {
			return fail(400, {
				error: error instanceof Error ? error.message : 'Failed to create user.'
			});
		}
	}
};
