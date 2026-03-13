import type { PageLoad } from './$types';
import type { HomeStats } from '$lib/types';

const EMPTY_STATS: HomeStats = {
	organizations: 0,
	individuals: 0,
	public_bodies: 0,
	datasets: 0,
	total_actors: 0,
	by_schema: {},
	top_lobbying_companies: [],
	top_organizations: []
};

export const load: PageLoad = async ({ fetch }) => {
	try {
		const res = await fetch('/api/stats');
		if (!res.ok) {
			return { stats: EMPTY_STATS };
		}
		const stats = (await res.json()) as HomeStats;
		return { stats };
	} catch {
		return { stats: EMPTY_STATS };
	}
};
