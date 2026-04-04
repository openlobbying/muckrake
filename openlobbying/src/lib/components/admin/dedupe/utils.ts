import type { Entity } from '$lib/types';
import { getEntityRoute } from '$lib/util/routes';

export function getEntityName(entity: Entity): string {
	return String(entity.properties.name?.[0] ?? entity.caption ?? entity.id);
}

export function getEntityDatasets(entity: Entity): string[] {
	return (entity.datasets ?? []).map((dataset) => dataset.title || dataset.name);
}

export function getEntityHref(entity: Entity): string {
	return getEntityRoute(entity.id, entity.schema);
}

export function formatLockExpiry(expiresAt?: string): string | null {
	if (!expiresAt) {
		return null;
	}

	const parsed = new Date(expiresAt);
	if (Number.isNaN(parsed.getTime())) {
		return null;
	}

	return parsed.toLocaleString('en-GB');
}
