import { fail } from '@sveltejs/kit';
import { getAdminApiHeaders, getMuckrakeApiBaseUrl, requireAdmin } from '$lib/server/admin';
import { getAdminErrorMessage, requireDedupeUser } from '$lib/server/admin-dedupe';
import type { DedupeClusterCandidate } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

interface DedupeClusterResponse {
	candidate: DedupeClusterCandidate | null;
}

async function loadCandidate(
	fetch: typeof globalThis.fetch,
	user: { id: string; name?: string | null }
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
	judge: async ({ locals, url, request, fetch }) => {
		requireAdmin(locals, url);
		const user = requireDedupeUser(locals);

		const formData = await request.formData();
		const intent = String(formData.get('intent') ?? 'match').trim();
		const entityIds = formData
			.getAll('entityId')
			.map((value) => String(value).trim())
			.filter(Boolean);
		const selectedIds = (intent === 'skip'
			? []
			: formData
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

		const response = await fetch(`${getMuckrakeApiBaseUrl()}/admin/dedupe-clusters/judge`, {
			method: 'POST',
			headers: {
				'content-type': 'application/json',
				...getAdminApiHeaders()
			},
			body: JSON.stringify({
				entity_ids: entityIds,
				selected_ids: selectedIds,
				locked_pairs: lockedPairs,
				intent,
				user_id: user.id,
				user_name: user.name
			})
		});

		if (!response.ok) {
			return fail(response.status, {
				error: await getAdminErrorMessage(response, 'Failed to save cluster merge.')
			});
		}

		return {
			success:
				intent === 'skip'
					? 'Skipped this cluster.'
					: intent === 'match'
						? `Recorded match judgements for ${selectedIds.length} selected records.`
						: intent === 'no_match'
							? `Recorded no-match judgements for ${selectedIds.length} selected records.`
							: `Recorded unsure judgements for ${selectedIds.length} selected records.`
		};
	}
};
