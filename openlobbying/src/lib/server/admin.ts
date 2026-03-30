import { redirect, error } from '@sveltejs/kit';
import { ADMIN_USER_ID, getAuthSecret } from '$lib/server/auth';

export function requireAdmin(locals: App.Locals, url: URL): void {
	if (!locals.user || !locals.session) {
		const redirectTo = `${url.pathname}${url.search}`;
		redirect(303, `/login?redirectTo=${encodeURIComponent(redirectTo)}`);
	}

	if (locals.user.id !== ADMIN_USER_ID) {
		redirect(303, '/account');
	}
}

export function getMuckrakeApiBaseUrl(): string {
	return process.env.MUCKRAKE_API_URL || 'http://127.0.0.1:8000';
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