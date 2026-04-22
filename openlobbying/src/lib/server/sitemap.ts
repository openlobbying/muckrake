import { error } from '@sveltejs/kit';
import { getMuckrakeApiBaseUrl } from '$lib/server/muckrake-api';
import type { HomeStats, ProfileSitemapResponse } from '$lib/types';

export const PROFILE_SITEMAP_LIMIT = 50000;

export const STATIC_SITEMAP_PATHS = [
	'/',
	'/about',
	'/datasets',
	'/licence',
	'/privacy'
] as const;

export const XML_HEADERS = {
	'content-type': 'application/xml; charset=utf-8',
	'cache-control': 'public, max-age=3600'
} as const;

export function getAbsoluteUrl(origin: string, path: string): string {
	return new URL(path, `${origin}/`).toString();
}

export function renderSitemapIndex(locations: string[]): string {
	const items = locations
		.map((location) => `  <sitemap><loc>${escapeXml(location)}</loc></sitemap>`)
		.join('\n');

	return [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
		items,
		'</sitemapindex>'
	].join('\n');
}

export function renderUrlSet(locations: string[]): string {
	const items = locations.map((location) => `  <url><loc>${escapeXml(location)}</loc></url>`).join('\n');

	return [
		'<?xml version="1.0" encoding="UTF-8"?>',
		'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
		items,
		'</urlset>'
	].join('\n');
}

export async function getActorCount(): Promise<number> {
	const response = await fetch(`${getMuckrakeApiBaseUrl()}/stats`);
	if (!response.ok) {
		throw error(response.status, 'Could not fetch actor counts for sitemap');
	}

	const stats = (await response.json()) as HomeStats;
	return stats.total_actors;
}

export async function getProfileSitemapPage(page: number): Promise<ProfileSitemapResponse> {
	const offset = (page - 1) * PROFILE_SITEMAP_LIMIT;
	const endpoint = new URL('/sitemaps/profiles', `${getMuckrakeApiBaseUrl()}/`);
	endpoint.searchParams.set('limit', String(PROFILE_SITEMAP_LIMIT));
	endpoint.searchParams.set('offset', String(offset));

	const response = await fetch(endpoint);
	if (!response.ok) {
		throw error(response.status, 'Could not fetch profile sitemap data');
	}

	return (await response.json()) as ProfileSitemapResponse;
}

function escapeXml(value: string): string {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&apos;');
}
