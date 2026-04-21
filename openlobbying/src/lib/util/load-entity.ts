import { error, redirect } from '@sveltejs/kit';
import type { Entity } from '$lib/types';

type RoutedEntity = Entity & { redirect?: boolean; correct_route?: string };

export async function loadEntity(fetchFn: typeof fetch, path: string, message: string): Promise<Entity> {
	const res = await fetchFn(path);
	if (!res.ok) {
		throw error(res.status, message);
	}

	const data = (await res.json()) as RoutedEntity;
	if (data.redirect && data.correct_route) {
		throw redirect(307, data.correct_route);
	}

	return data;
}
