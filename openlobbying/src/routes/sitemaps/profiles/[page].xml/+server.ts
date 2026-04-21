import { error } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import {
	XML_HEADERS,
	getAbsoluteUrl,
	getProfileSitemapPage,
	renderUrlSet
} from '$lib/server/sitemap';

export const GET: RequestHandler = async ({ params, url }) => {
	const page = Number.parseInt(params.page, 10);
	if (!Number.isInteger(page) || page < 1) {
		throw error(404, 'Sitemap page not found');
	}

	const sitemapPage = await getProfileSitemapPage(page);
	if (page > 1 && sitemapPage.results.length === 0) {
		throw error(404, 'Sitemap page not found');
	}

	const locations = sitemapPage.results.map((entry) => getAbsoluteUrl(url.origin, entry.path));

	return new Response(renderUrlSet(locations), {
		headers: XML_HEADERS
	});
};
