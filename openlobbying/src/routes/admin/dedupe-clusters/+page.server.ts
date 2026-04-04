import { fail } from '@sveltejs/kit';
import { getAdminApiHeaders, getMuckrakeApiBaseUrl, requireAdmin } from '$lib/server/admin';
import type { DedupeClusterCandidate } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

interface DedupeClusterResponse {
	candidate: DedupeClusterCandidate | null;
}

interface DedupeUser {
	id: string;
	name?: string | null;
}

function requireDedupeUser(locals: App.Locals): DedupeUser {
	const user = locals.user;
	if (!user) {
		throw new Error('Authenticated admin user missing from request context.');
	}

	return {
		id: user.id,
		name: user.name
	};
}

async function getErrorMessage(response: Response, fallback: string): Promise<string> {
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

async function loadCandidate(
	fetch: typeof globalThis.fetch,
	user: DedupeUser
): Promise<DedupeClusterCandidate | null> {
	const endpoint = new URL(`${getMuckrakeApiBaseUrl()}/admin/dedupe-clusters/next`);
	endpoint.searchParams.set('user_id', user.id);
	if (user.name) {
		endpoint.searchParams.set('user_name', user.name);
	}

	const response = await fetch(endpoint.toString(), {
		headers: getAdminApiHeaders()
	});

	if (!response.ok) {
		throw new Error(await response.text());
	}

	const payload = (await response.json()) as DedupeClusterResponse;
	return payload.candidate;
}

export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	requireAdmin(locals, url);
	const user = requireDedupeUser(locals);

	return {
		candidate: await loadCandidate(fetch, user)
	};
};

export const actions: Actions = {
	merge: async ({ locals, url, request, fetch }) => {
		requireAdmin(locals, url);
		const user = requireDedupeUser(locals);

		const formData = await request.formData();
		const intent = String(formData.get('intent') ?? 'merge').trim();
		const entityIds = formData
			.getAll('entityId')
			.map((value) => String(value).trim())
			.filter(Boolean);
		const selectedIds = (intent === 'skip' ? [] : formData
			.getAll('selectedId')
			.map((value) => String(value).trim())
			.filter(Boolean));
		const lockedPairs = formData
			.getAll('lockedPair')
			.map((value) => String(value).trim())
			.filter(Boolean)
			.map((pair) => {
				const [leftId, rightId] = pair.split('::');
				return {
					left_id: leftId,
					right_id: rightId
				};
			});

		if (entityIds.length < 2 || lockedPairs.length === 0) {
			return fail(400, {
				error: 'Missing cluster members or locked pair data.'
			});
		}

		const response = await fetch(`${getMuckrakeApiBaseUrl()}/admin/dedupe-clusters/merge`, {
			method: 'POST',
			headers: {
				'content-type': 'application/json',
				...getAdminApiHeaders()
			},
			body: JSON.stringify({
				entity_ids: entityIds,
				selected_ids: selectedIds,
				locked_pairs: lockedPairs,
				user_id: user.id,
				user_name: user.name
			})
		});

		if (!response.ok) {
			return fail(response.status, {
				error: await getErrorMessage(response, 'Failed to save cluster merge.')
			});
		}

		return {
			success:
				intent === 'skip'
					? 'Skipped this cluster.'
					: selectedIds.length >= 2
					? `Merged ${selectedIds.length} selected records and marked ${entityIds.length - selectedIds.length} unchecked records as no match.`
					: 'Released the cluster without merging records.'
		};
	}
};
