import { fail } from '@sveltejs/kit';
import { getAdminApiHeaders, getMuckrakeApiBaseUrl, requireAdmin } from '$lib/server/admin';
import type { DedupeCandidate } from '$lib/types';
import type { Actions, PageServerLoad } from './$types';

interface DedupeCandidateResponse {
	candidate: DedupeCandidate | null;
}

async function loadCandidate(fetch: typeof globalThis.fetch): Promise<DedupeCandidate | null> {
	const response = await fetch(`${getMuckrakeApiBaseUrl()}/admin/dedupe/next`, {
		headers: getAdminApiHeaders()
	});

	if (!response.ok) {
		throw new Error(await response.text());
	}

	const payload = (await response.json()) as DedupeCandidateResponse;
	return payload.candidate;
}

export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	requireAdmin(locals, url);

	return {
		candidate: await loadCandidate(fetch)
	};
};

export const actions: Actions = {
	judge: async ({ locals, url, request, fetch }) => {
		requireAdmin(locals, url);

		const formData = await request.formData();
		const leftId = String(formData.get('leftId') ?? '').trim();
		const rightId = String(formData.get('rightId') ?? '').trim();
		const judgement = String(formData.get('judgement') ?? '').trim();

		if (!leftId || !rightId || !judgement) {
			return fail(400, {
				error: 'Missing candidate identifiers or judgement.'
			});
		}

		const response = await fetch(`${getMuckrakeApiBaseUrl()}/admin/dedupe/judge`, {
			method: 'POST',
			headers: {
				'content-type': 'application/json',
				...getAdminApiHeaders()
			},
			body: JSON.stringify({
				left_id: leftId,
				right_id: rightId,
				judgement
			})
		});

		if (!response.ok) {
			return fail(response.status, {
				error: (await response.text()) || 'Failed to save dedupe judgement.'
			});
		}

		return {
			success: `Recorded ${judgement.replace('_', ' ')} judgement.`
		};
	}
};