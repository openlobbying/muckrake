import type { PageLoad } from './$types';
import { error } from '@sveltejs/kit';

export const load: PageLoad = async ({ params, fetch }) => {
	const res = await fetch(`/api/entities/${params.id}`);
	
	if (!res.ok) {
		error(res.status, 'Could not fetch entity');
	}

	const entity = await res.json();
	return { entity };
};
