import type { PageLoad } from './$types';
import { error, redirect } from '@sveltejs/kit';
import type { Entity } from '$lib/types';

export const load: PageLoad = async ({ params, fetch }) => {
	const entity = fetch(`/api/profiles/${params.id}`).then(async (res) => {
		if (!res.ok) {
			throw error(res.status, 'Could not fetch profile');
		}

		const data = (await res.json()) as Entity & { redirect?: boolean; correct_route?: string };

		if (data.redirect && data.correct_route) {
			throw redirect(307, data.correct_route);
		}

		return data as Entity;
	});

	return { entity };
};
