import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	if (!locals.user || !locals.session) {
		const redirectTo = `${url.pathname}${url.search}`;
		redirect(303, `/login?redirectTo=${encodeURIComponent(redirectTo)}`);
	}

	return {
		session: locals.session,
		user: locals.user
	};
};
