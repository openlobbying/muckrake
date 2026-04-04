export interface DedupeUser {
	id: string;
	name?: string | null;
}

export function requireDedupeUser(locals: App.Locals): DedupeUser {
	const user = locals.user;
	if (!user) {
		throw new Error('Authenticated admin user missing from request context.');
	}

	return {
		id: user.id,
		name: user.name
	};
}

export async function getAdminErrorMessage(response: Response, fallback: string): Promise<string> {
	const text = (await response.text()).trim();
	if (!text) {
		return fallback;
	}

	try {
		const payload = JSON.parse(text) as { detail?: string };
		return payload.detail || fallback;
	} catch {
		return text;
	}
}
