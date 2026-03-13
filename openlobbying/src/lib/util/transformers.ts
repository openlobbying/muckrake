import type {
	Entity,
	TimelineItem,
	RelationshipGroup,
	RelationshipItem,
	RelationshipPeriod,
} from "../types";
import { formatQuarterRange, getBestDate } from "./dates";

export function transformActivities(entity: Entity): TimelineItem[] {
    if (!entity.adjacent) return [];

    const items: TimelineItem[] = [];
    for (const [_, group] of Object.entries(entity.adjacent)) {
        for (const item of group.results) {
            const schema = item.schema;
            if (schema === "Employment") {
                continue;
            }
            let type = schema;
            let title = item.caption;
            let description = (item.properties.description?.[0] as string) || "";
            let date = getBestDate(item.properties) || "";
            let amount = item.properties.amount?.[0] as string | undefined;

            if (schema === "Event") {
                if (
                    item.properties.keywords?.some(
                        (k: string) =>
                            k.includes("Oral Evidence") ||
                            k.includes("Written Evidence"),
                    )
                ) {
                    type = "Evidence";
                } else if (
                    item.properties.keywords?.some((k: string) =>
                        k.includes("Meeting"),
                    )
                ) {
                    type = "Meeting";
                } else if (
                    item.properties.country && 
                    item.properties.country.length > 0
                ) {
                    // Visits outside UK have country property
                    type = "Visit";
                }
            } else if (schema === "Trip") {
                // Trip entities from register of interests
                type = "Trip";
            } else if (schema === "Representation") {
                title = (item.properties.role?.[0] as string) || item.caption;
            } else if (schema === "Payment") {
                // Distinguish between different payment types
                const purpose = item.properties.purpose?.[0] as string;
                const summary = item.properties.summary?.[0] as string;
                
                // Check if it's a gift or donation based on purpose/summary
                if (purpose?.toLowerCase().includes("gift") || 
                    summary?.toLowerCase().includes("gift")) {
                    type = "Gift";
                } else if (purpose?.toLowerCase().includes("donation") || 
                          summary?.toLowerCase().includes("donation") ||
                          summary?.toLowerCase().includes("support")) {
                    type = "Donation";
                }
            } else if (schema === "Ownership") {
                const asset = item.properties.asset?.[0];
                // Determine if it's property or shareholding based on asset schema
                if (asset?.schema === "Asset") {
                    type = "Property";
                }
            } else if (schema === "Directorship") {
            } else if (schema === "Family") {
                const relationship = item.properties.relationship?.[0] as string;
                title = relationship || "Family member";
            } else if (schema === "UnknownLink") {
                // Miscellaneous interests
            } else if (schema === "PublicDisclosure") {
                // Public disclosure statement
            } else {
                // Skip unknown schemas
                continue;
            }

            items.push({
                id: item.id,
                type,
                title,
                description,
                date,
                amount,
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

    const toDateToken = (value: unknown): string | undefined => {
        if (typeof value !== "string") return undefined;
        if (/^\d{4}-\d{2}$/.test(value) || /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
        return undefined;
    };

    const relationshipUsesQuarterLabels = (datasetNames?: string[]): boolean => {
        if (!datasetNames || datasetNames.length === 0) return false;
        return datasetNames.some((name) => name === "orcl" || name === "gb_prca");
    };

    const toDateBoundary = (value: string, end = false): Date | undefined => {
        if (/^\d{4}-\d{2}$/.test(value)) {
            const [year, month] = value.split("-").map(Number);
            const day = end ? new Date(Date.UTC(year, month, 0)).getUTCDate() : 1;
            return new Date(Date.UTC(year, month - 1, day));
        }
        if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
            return new Date(`${value}T00:00:00Z`);
        }
        return undefined;
    };

    const formatDate = (value?: string): string | undefined => {
        if (!value) return undefined;
        const monthOnly = /^(\d{4})-(\d{2})$/.exec(value);
        if (monthOnly) {
            const date = new Date(Date.UTC(Number(monthOnly[1]), Number(monthOnly[2]) - 1, 1));
            return date.toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
        }
        const full = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
        if (full) {
            const date = new Date(Date.UTC(Number(full[1]), Number(full[2]) - 1, Number(full[3])));
            return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
        }
        return value;
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

        const start = formatDate(startDate);
        const end = formatDate(endDate);
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
            const periodStart = toDateToken(item.startDate);
            const periodEnd = toDateToken(item.endDate);
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
            const schema = item.schema;
            const props = item.properties;

            if (schema === "Employment") {
                const employees = props.employee || [];
                const employers = props.employer || [];

                if (employees.some((e: Record<string, unknown>) => e.id === currentId)) {
                    for (const employer of employers) {
                        groups.employers.push({
                            id: String((employer as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((employer as Record<string, unknown>).caption || ""),
                            schema: String((employer as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
                if (employers.some((e: Record<string, unknown>) => e.id === currentId)) {
                    for (const employee of employees) {
                        groups.employees.push({
                            id: String((employee as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((employee as Record<string, unknown>).caption || ""),
                            schema: String((employee as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
            } else if (schema === "Membership") {
                const members = props.member || [];
                const organizations = props.organization || [];

                if (members.some((m: Record<string, unknown>) => m.id === currentId)) {
                    for (const organization of organizations) {
                        groups.organizations.push({
                            id: String((organization as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((organization as Record<string, unknown>).caption || ""),
                            schema: String((organization as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
                if (organizations.some((o: Record<string, unknown>) => o.id === currentId)) {
                    for (const member of members) {
                        groups.members.push({
                            id: String((member as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((member as Record<string, unknown>).caption || ""),
                            schema: String((member as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
            } else if (schema === "Representation") {
                const agents = props.agent || [];
                const clients = props.client || [];

                if (clients.some((c: Record<string, unknown>) => c.id === currentId)) {
                    for (const agent of agents) {
                        groups.lobbyists.push({
                            id: String((agent as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((agent as Record<string, unknown>).caption || ""),
                            schema: String((agent as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
                if (agents.some((a: Record<string, unknown>) => a.id === currentId)) {
                    for (const client of clients) {
                        groups.clients.push({
                            id: String((client as Record<string, unknown>).id || ""),
                            statementId: item.id,
                            name: String((client as Record<string, unknown>).caption || ""),
                            schema: String((client as Record<string, unknown>).schema || "Entity"),
                            role: props.role?.[0],
                            startDate: props.startDate?.[0],
                            endDate: props.endDate?.[0],
                            datasetNames: (item.datasets || []).map((d: { name?: string }) => String(d?.name || "")).filter(Boolean),
                        });
                    }
                }
            }
        }
    }

    return Object.entries(groups)
        .filter(([_, items]) => items.length > 0)
        .map(([type, items]) => ({ type, items: groupRelationshipItems(items) }));
}
