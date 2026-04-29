import type { PageLoad } from './$types';
import { loadEntity } from '$lib/util/load-entity';

export const load: PageLoad = async ({ params, fetch }) => {
	return {
		entity: await loadEntity(fetch, `/api/statement/${params.id}`, 'Could not fetch statement')
	};
};
