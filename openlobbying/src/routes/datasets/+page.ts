import type { PageLoad } from './$types';
import { error } from '@sveltejs/kit';
import type { DatasetMetadata } from '$lib/types';

export const load: PageLoad = async ({ fetch }) => {
	const res = await fetch('/api/datasets');
	
	if (!res.ok) {
		throw error(res.status, 'Could not fetch datasets');
	}

	const datasets = (await res.json()) as DatasetMetadata[];
	return { datasets };
};
