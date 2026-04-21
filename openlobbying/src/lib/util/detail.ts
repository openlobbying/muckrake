import { getEntityRoute } from '$lib/util/routes';

export interface DetailRow {
	key: string;
	values: any[];
}

export function formatLabel(label: string): string {
	return label.replace(/([A-Z])/g, ' $1').replace(/^./, (char) => char.toUpperCase());
}

export function isEntity(value: any): value is { id: string; caption: string; schema?: string } {
	return typeof value === 'object' && value !== null && 'id' in value && 'caption' in value;
}

export function isUrl(value: unknown): value is string {
	return typeof value === 'string' && /^https?:\/\//.test(value);
}

export function normalizeValue(value: any): string {
	if (value == null) return '';
	if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
		return String(value);
	}
	if (Array.isArray(value)) {
		return value.map((item) => normalizeValue(item)).filter(Boolean).join(', ');
	}
	if (typeof value === 'object') {
		if (value.caption) return String(value.caption);
		if (value.name) return String(value.name);
		return JSON.stringify(value);
	}
	return '';
}

export function buildRowsForKeys(
	properties: Record<string, any[]> | undefined,
	keys: string[]
): DetailRow[] {
	if (!properties || keys.length === 0) return [];

	const rows: DetailRow[] = [];
	for (const key of keys) {
		const values = properties[key];
		if (!Array.isArray(values) || values.length === 0) continue;
		const filtered = values.filter((value) => Boolean(normalizeValue(value)));
		if (filtered.length > 0) {
			rows.push({ key, values: filtered });
		}
	}

	return rows;
}

export function buildRemainingRows(
	properties: Record<string, any[]> | undefined,
	excludedKeys: Set<string>
): DetailRow[] {
	if (!properties) return [];

	const keys = Object.keys(properties)
		.filter((key) => !excludedKeys.has(key))
		.sort();

	return buildRowsForKeys(properties, keys);
}

export function renderableValue(value: any, key: string) {
	if (isEntity(value)) {
		return {
			type: 'entity' as const,
			href: getEntityRoute(value.id, value.schema || 'Entity'),
			text: value.caption
		};
	}

	if (key === 'sourceUrl' && isUrl(value)) {
		return {
			type: 'url' as const,
			href: value,
			text: value
		};
	}

	return {
		type: 'text' as const,
		text: normalizeValue(value)
	};
}
