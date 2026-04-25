import type { PageLoad } from './$types';
import { loadEntity } from '$lib/util/load-entity';

export const load: PageLoad = async ({ params, fetch }) => {
	const entity = await loadEntity(fetch, `/api/profiles/${params.id}`, 'Could not fetch profile');

	return { entity };
};
