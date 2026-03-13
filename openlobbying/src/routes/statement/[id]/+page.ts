import type { PageLoad } from './$types';
import { error, redirect } from '@sveltejs/kit';

export const load: PageLoad = async ({ params, fetch }) => {
	// We use the 'statements' endpoint which implies nested=False (no timeline)
	const res = await fetch(`/api/statements/${params.id}`);
	
	if (!res.ok) {
		error(res.status, 'Could not fetch statement');
	}

	const data = await res.json();
	
	// Check if API returned a redirect
	if (data.redirect) {
		redirect(307, data.correct_route);
	}

	return { entity: data };
};
