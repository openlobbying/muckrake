import type { RequestHandler } from './$types';
import {
	STATIC_SITEMAP_PATHS,
	XML_HEADERS,
	getAbsoluteUrl,
	renderUrlSet
} from '$lib/server/sitemap';

export const GET: RequestHandler = async ({ url }) => {
	const locations = STATIC_SITEMAP_PATHS.map((path) => getAbsoluteUrl(url.origin, path));

	return new Response(renderUrlSet(locations), {
		headers: XML_HEADERS
	});
};
