import type { RequestHandler } from './$types';
import {
	PROFILE_SITEMAP_LIMIT,
	XML_HEADERS,
	getAbsoluteUrl,
	getActorCount,
	renderSitemapIndex
} from '$lib/server/sitemap';

export const GET: RequestHandler = async ({ url }) => {
	const locations = [getAbsoluteUrl(url.origin, '/sitemaps/static.xml')];
	const actorCount = await getActorCount();
	const profileSitemapCount = Math.ceil(actorCount / PROFILE_SITEMAP_LIMIT);

	for (let page = 1; page <= profileSitemapCount; page += 1) {
		locations.push(getAbsoluteUrl(url.origin, `/sitemaps/profiles/${page}.xml`));
	}

	return new Response(renderSitemapIndex(locations), {
		headers: XML_HEADERS
	});
};
