import type {
	Entity,
	TimelineItem,
	RelationshipGroup,
	RelationshipItem,
	RelationshipPeriod,
} from "../types";
import {
	formatDateToken,
	formatQuarterRange,
	getBestDate,
	isDateToken,
	toDateBoundary,
} from "./dates";

type RelationshipDefinition = {
	schema: string;
	leftProp: string;
	rightProp: string;
	leftGroup: string;
	rightGroup: string;
};

type EntityRef = {
	id: string;
	caption: string;
	schema: string;
};

const TIMELINE_SCHEMAS = new Set([
	'Event',
	'Meeting',
	'Hospitality',
	'Trip',
	'Representation',
	'Payment',
	'Donation',
	'Gift',
	'Ownership',
	'Directorship',
	'Family',
	'UnknownLink',
	'PublicDisclosure'
]);

const RELATIONSHIP_DEFINITIONS: RelationshipDefinition[] = [
	{
		schema: 'Employment',
		leftProp: 'employee',
		rightProp: 'employer',
		leftGroup: 'employers',
		rightGroup: 'employees'
	},
	{
		schema: 'Membership',
		leftProp: 'member',
		rightProp: 'organization',
		leftGroup: 'organizations',
		rightGroup: 'members'
	},
	{
		schema: 'Representation',
		leftProp: 'client',
		rightProp: 'agent',
		leftGroup: 'lobbyists',
		rightGroup: 'clients'
	}
];

function getStringProp(item: Entity, key: string): string | undefined {
	const value = item.properties[key]?.[0];
	return typeof value === 'string' ? value : undefined;
}

function hasKeyword(item: Entity, needle: string): boolean {
	return item.properties.keywords?.some((keyword: string) => keyword.includes(needle)) ?? false;
}

function getActivityType(item: Entity): string | null {
	if (!TIMELINE_SCHEMAS.has(item.schema)) {
		return null;
	}

	if (item.schema === 'Event') {
		if (hasKeyword(item, 'Oral Evidence') || hasKeyword(item, 'Written Evidence')) {
			return 'Evidence';
		}
		if (hasKeyword(item, 'Meeting')) {
			return 'Meeting';
		}
		return item.properties.country?.length ? 'Visit' : 'Event';
	}

	if (item.schema === 'Payment') {
		const purpose = getStringProp(item, 'purpose')?.toLowerCase() || '';
		const summary = getStringProp(item, 'summary')?.toLowerCase() || '';
		if (purpose.includes('gift') || summary.includes('gift')) {
			return 'Gift';
		}
		if (
			purpose.includes('donation') ||
			summary.includes('donation') ||
			summary.includes('support')
		) {
			return 'Donation';
		}
	}

	if (
		item.schema === 'Meeting' ||
		item.schema === 'Donation' ||
		item.schema === 'Gift' ||
		item.schema === 'Hospitality'
	) {
		return item.schema;
	}

	if (item.schema === 'Ownership' && item.properties.asset?.[0]?.schema === 'Asset') {
		return 'Property';
	}

	return item.schema;
}

function getActivityTitle(item: Entity): string {
	if (item.schema === 'Representation') {
		return getStringProp(item, 'role') || item.caption;
	}

	if (item.schema === 'Family') {
		return getStringProp(item, 'relationship') || 'Family member';
	}

	return item.caption;
}

function getDatasetNames(item: Entity): string[] {
	return (item.datasets || [])
		.map((dataset) => String(dataset?.name || ''))
		.filter(Boolean);
}

function getEntityRefs(values: unknown[]): EntityRef[] {
	return values.flatMap((value) => {
		if (!value || typeof value !== 'object') {
			return [];
		}

		const ref = value as Record<string, unknown>;
		const id = typeof ref.id === 'string' ? ref.id : '';
		if (!id) {
			return [];
		}

		return [
			{
				id,
				caption: typeof ref.caption === 'string' ? ref.caption : '',
				schema: typeof ref.schema === 'string' ? ref.schema : 'Entity'
			}
		];
	});
}

function buildRelationshipItems(item: Entity, refs: EntityRef[]): RelationshipItem[] {
	const role = getStringProp(item, 'role');
	const startDate = getStringProp(item, 'startDate');
	const endDate = getStringProp(item, 'endDate');
	const datasetNames = getDatasetNames(item);

	return refs.map((ref) => ({
		id: ref.id,
		statementId: item.id,
		name: ref.caption,
		schema: ref.schema,
		role,
		startDate,
		endDate,
		datasetNames,
	}));
}

export function transformActivities(entity: Entity): TimelineItem[] {
    if (!entity.adjacent) return [];

    const items: TimelineItem[] = [];
    for (const [_, group] of Object.entries(entity.adjacent)) {
        for (const item of group.results) {
			const type = getActivityType(item);
			if (type === null) {
				continue;
			}

			items.push({
				id: item.id,
				type,
				title: getActivityTitle(item),
				description: getStringProp(item, 'description') || '',
				date: getBestDate(item.properties) || '',
				amount: getStringProp(item, 'amount'),
				properties: item.properties,
				schema: item.schema,
				datasets: item.datasets,
			});
        }
    }
    return items.sort((a, b) => b.date.localeCompare(a.date));
}

export function transformRelationships(entity: Entity): RelationshipGroup[] {
    if (!entity.adjacent) return [];

    const relationshipUsesQuarterLabels = (datasetNames?: string[]): boolean => {
        if (!datasetNames || datasetNames.length === 0) return false;
        return datasetNames.some((name) => name === "orcl" || name === "gb_prca");
    };

    const formatPeriodLabel = (
        startDate?: string,
        endDate?: string,
        datasetNames?: string[],
    ): string | undefined => {
        if (relationshipUsesQuarterLabels(datasetNames)) {
            const quarterRange = formatQuarterRange(startDate, endDate);
            return quarterRange === "Unknown Date" ? undefined : quarterRange;
        }

		const start = formatDateToken(startDate);
		const end = formatDateToken(endDate);
        if (!start && !end) return undefined;
        if (start && end && start === end) return start;
        return `${start || ""} - ${end || ""}`;
    };

    const dedupeAndSortPeriods = (periods: RelationshipPeriod[]): RelationshipPeriod[] => {
        const seen = new Set<string>();
        const unique: RelationshipPeriod[] = [];
        for (const period of periods) {
            const key = `${period.startDate || ""}|${period.endDate || ""}|${period.statementId || ""}`;
            if (seen.has(key)) continue;
            seen.add(key);
            unique.push(period);
        }

        unique.sort((a, b) => {
            const aStart = a.startDate || "";
            const bStart = b.startDate || "";
            if (aStart !== bStart) return aStart.localeCompare(bStart);
            const aEnd = a.endDate || "";
            const bEnd = b.endDate || "";
            if (aEnd !== bEnd) return aEnd.localeCompare(bEnd);
            return (a.statementId || "").localeCompare(b.statementId || "");
        });
        return unique;
    };

    const areContinuous = (a: RelationshipPeriod, b: RelationshipPeriod): boolean => {
        if (!a.endDate || !b.startDate) return false;
        const end = toDateBoundary(a.endDate, true);
        const start = toDateBoundary(b.startDate, false);
        if (!end || !start) return false;
        const oneDayMs = 24 * 60 * 60 * 1000;
        return start.getTime() <= end.getTime() + oneDayMs;
    };

    const mergeContinuousPeriods = (periods: RelationshipPeriod[]): RelationshipPeriod[] => {
        const sorted = dedupeAndSortPeriods(periods);
        if (sorted.length === 0) return [];

        const merged: RelationshipPeriod[] = [];
        let chain: RelationshipPeriod[] = [sorted[0]];

        const flush = () => {
            if (!chain.length) return;
            const startDate = chain[0].startDate;
            const endDate = chain[chain.length - 1].endDate;
            const datasetNames = Array.from(
                new Set(
                    chain.flatMap((period) => period.datasetNames || []),
                ),
            );
            const statementIds = chain
                .map((period) => period.statementId)
                .filter((id): id is string => typeof id === "string");
            const label = formatPeriodLabel(startDate, endDate, datasetNames) || "";
            merged.push({
                label,
                statementId: statementIds[0],
                statementIds,
                startDate,
                endDate,
                datasetNames,
            });
            chain = [];
        };

        for (let i = 1; i < sorted.length; i += 1) {
            const current = sorted[i];
            const previous = chain[chain.length - 1];
            if (areContinuous(previous, current)) {
                chain.push(current);
                continue;
            }
            flush();
            chain = [current];
        }
        flush();
        return merged;
    };

    const groupRelationshipItems = (items: RelationshipItem[]): RelationshipItem[] => {
        const grouped = new Map<string, RelationshipItem>();
        for (const item of items) {
            const key = [item.id, item.schema, item.role || ""].join("|");
			const periodStart = isDateToken(item.startDate) ? item.startDate : undefined;
			const periodEnd = isDateToken(item.endDate) ? item.endDate : undefined;
            const period: RelationshipPeriod | undefined = periodStart || periodEnd
                ? {
                    label: formatPeriodLabel(periodStart, periodEnd, item.datasetNames) || "",
                    statementId: item.statementId,
                    startDate: periodStart,
                    endDate: periodEnd,
                    datasetNames: item.datasetNames,
                }
                : undefined;

            const existing = grouped.get(key);
            if (!existing) {
                grouped.set(key, {
                    id: item.id,
                    name: item.name,
                    schema: item.schema,
                    role: item.role,
                    datasetNames: item.datasetNames,
                    periods: period ? [period] : [],
                });
                continue;
            }

            if (period) {
                existing.periods = [...(existing.periods || []), period];
            }
        }

        const output = Array.from(grouped.values());
        for (const item of output) {
            item.periods = mergeContinuousPeriods(item.periods || []);
            item.activePeriod = item.periods
                .map((period) => period.label)
                .filter((label) => label.length > 0)
                .join("; ");
        }
        output.sort((a, b) => a.name.localeCompare(b.name));
        return output;
    };

    const groups: Record<string, RelationshipItem[]> = {
        lobbyists: [],
        clients: [],
        employers: [],
        employees: [],
        organizations: [],
        members: [],
    };

	const currentId = entity.id;

    for (const [_, group] of Object.entries(entity.adjacent)) {
        for (const item of group.results) {
			const definition = RELATIONSHIP_DEFINITIONS.find(
				(definition) => definition.schema === item.schema
			);
			if (!definition) {
				continue;
			}

			const leftRefs = getEntityRefs(item.properties[definition.leftProp] || []);
			const rightRefs = getEntityRefs(item.properties[definition.rightProp] || []);

			if (leftRefs.some((ref) => ref.id === currentId)) {
				groups[definition.leftGroup].push(...buildRelationshipItems(item, rightRefs));
			}
			if (rightRefs.some((ref) => ref.id === currentId)) {
				groups[definition.rightGroup].push(...buildRelationshipItems(item, leftRefs));
			}
        }
    }

    return Object.entries(groups)
        .filter(([_, items]) => items.length > 0)
        .map(([type, items]) => ({ type, items: groupRelationshipItems(items) }));
}
