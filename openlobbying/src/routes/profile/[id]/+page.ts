import type { PageLoad } from './$types';
import { loadEntity } from '$lib/util/load-entity';

export const load: PageLoad = async ({ params, fetch }) => {
	const entity = await loadEntity(
		fetch,
		`/api/profile/${params.id}?activity_limit=20&activity_offset=0`,
		'Could not fetch profile'
	);

	return { entity };
};
