import type { PageLoad } from './$types';
import { error } from '@sveltejs/kit';
import type { SearchResponse } from '$lib/types';

const DEFAULT_LIMIT = 20;
const ALLOWED_TYPES = ['Person', 'Company', 'Organization', 'PublicBody'] as const;

function parsePage(value: string | null): number {
	const page = Number(value ?? '1');
	if (!Number.isFinite(page) || page < 1) {
		return 1;
	}
	return Math.floor(page);
}

function parseType(value: string | null): string | null {
	if (!value) {
		return null;
	}
	if (ALLOWED_TYPES.includes(value as (typeof ALLOWED_TYPES)[number])) {
		return value;
	}
	return null;
}

export const load: PageLoad = async ({ fetch, url }) => {
	const q = (url.searchParams.get('q') ?? '').trim();
	const page = parsePage(url.searchParams.get('page'));
	const type = parseType(url.searchParams.get('type'));
	const offset = (page - 1) * DEFAULT_LIMIT;

	const empty: SearchResponse = {
		results: [],
		total: 0,
		offset,
		limit: DEFAULT_LIMIT,
		has_next: false,
		schema: []
	};

	if (!q) {
		return {
			query: '',
			page,
			type,
			search: Promise.resolve(empty)
		};
	}

	const params = new URLSearchParams();
	params.set('q', q);
	params.set('limit', String(DEFAULT_LIMIT));
	params.set('offset', String(offset));
	if (type) {
		params.set('schema', type);
	}

	const search = fetch(`/api/search?${params.toString()}`).then(async (res) => {
		if (!res.ok) {
			throw error(res.status, 'Could not fetch search results');
		}

		return (await res.json()) as SearchResponse;
	});

	return {
		query: q,
		page,
		type,
		search
	};
};
