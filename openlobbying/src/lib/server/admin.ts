import { redirect, error } from '@sveltejs/kit';
import { isAdminUser } from '$lib/auth-roles';
import { getAuthSecret } from '$lib/server/auth';
import { getMuckrakeApiBaseUrl } from '$lib/server/muckrake-api';

export { getMuckrakeApiBaseUrl };

export function requireAdmin(locals: App.Locals, url: URL): void {
	if (!locals.user || !locals.session) {
		const redirectTo = `${url.pathname}${url.search}`;
		redirect(303, `/login?redirectTo=${encodeURIComponent(redirectTo)}`);
	}

	if (!isAdminUser(locals.user)) {
		redirect(303, '/account');
	}
}

export function getAdminApiHeaders(): HeadersInit {
	return {
		'X-Admin-Secret': getAuthSecret()
	};
}

export async function expectJson<T>(response: Response, message: string): Promise<T> {
	if (!response.ok) {
		const detail = await response.text();
		throw error(response.status, detail || message);
	}

	return (await response.json()) as T;
}
