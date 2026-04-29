import {
	buildRemainingRows,
	buildRowsForKeys,
	type DetailRow
} from '$lib/util/detail';

interface PropertyProfile {
	primaryKeys: string[];
	secondaryKeys?: string[];
	labels?: Record<string, string>;
}

const DEFAULT_PROFILE: PropertyProfile = {
	primaryKeys: ['summary', 'description']
};

const PROFILES: Record<string, PropertyProfile> = {
	Payment: {
		primaryKeys: [],
		secondaryKeys: ['description', 'sourceUrl', 'recordId'],
		labels: {
			programme: 'Type'
		}
	},
	Donation: {
		primaryKeys: ['programme'],
		secondaryKeys: ['description', 'sourceUrl', 'recordId'],
		labels: {
			programme: 'Type'
		}
	},
	Gift: {
		primaryKeys: ['programme'],
		secondaryKeys: ['description', 'sourceUrl', 'recordId'],
		labels: {
			programme: 'Type'
		}
	},
	Hospitality: {
		primaryKeys: ['purpose', 'involved'],
		secondaryKeys: ['description', 'sourceUrl', 'recordId'],
		labels: {
			programme: 'Type'
		}
	},
	Meeting: {
		primaryKeys: ['summary', 'involved']
	},
	Evidence: {
		primaryKeys: ['name', 'involved']
	},
	Trip: {
		primaryKeys: ['summary', 'involved']
	},
	Visit: {
		primaryKeys: ['summary']
	},
	Ownership: {
		primaryKeys: ['description']
	},
	Property: {
		primaryKeys: ['description']
	},
	Representation: {
		primaryKeys: ['summary']
	},
	Employment: {
		primaryKeys: ['role', 'description']
	},
	Family: {
		primaryKeys: ['relationship', 'description']
	},
	UnknownLink: {
		primaryKeys: ['summary', 'description']
	}
};

function getProfile(type: string): PropertyProfile {
	return PROFILES[type] || DEFAULT_PROFILE;
}

export function getPropertyLabel(type: string, key: string): string {
	return getProfile(type).labels?.[key] || key;
}

export function getTimelinePrimaryRows(
	type: string,
	properties: Record<string, any[]> | undefined
): DetailRow[] {
	const profile = getProfile(type);
	return buildRowsForKeys(properties, profile.primaryKeys);
}

export function getTimelineDetailRows(
	type: string,
	properties: Record<string, any[]> | undefined
): DetailRow[] {
	const profile = getProfile(type);
	const secondaryRows = buildRowsForKeys(properties, profile.secondaryKeys || []);
	const consumed = new Set([...profile.primaryKeys, ...(profile.secondaryKeys || [])]);
	const restRows = buildRemainingRows(properties, consumed);
	return [...secondaryRows, ...restRows];
}

export function getStatementPropertyOrder(
	type: string,
	properties: Record<string, any[]> | undefined
): string[] {
	if (!properties) return [];
	const profile = getProfile(type);
	const keys = Object.keys(properties);
	const prioritized = profile.primaryKeys.filter((key) => keys.includes(key));
	const remaining = keys
		.filter((key) => !prioritized.includes(key))
		.sort((a, b) => a.localeCompare(b));
	return [...prioritized, ...remaining];
}
