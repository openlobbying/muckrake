import type {
	Entity,
	RelationshipGroup,
	RelationshipItem,
	RelationshipPeriod,
	TimelineItem,
} from "$lib/types";
import { formatQuarterRange, getBestDate } from "$lib/util/dates";

type AdjacentGroup = {
	results: Entity[];
	total: number;
};

const toDatasetNames = (datasets?: Array<{ name?: string }>): string[] => {
	if (!datasets) return [];
	return datasets
		.map((d) => (typeof d?.name === "string" ? d.name : ""))
		.filter((name) => name.length > 0);
};

export function transformActivities(entity: Entity): TimelineItem[] {
	if (!entity.adjacent) return [];

	const items: TimelineItem[] = [];
	for (const group of Object.values(entity.adjacent) as AdjacentGroup[]) {
		for (const item of group.results) {
			const schema = item.schema;
			if (schema === "Employment") continue;

			let type = schema;
			let title = item.caption;
			const properties = item.properties;
			const description = (properties.description?.[0] as string) || "";
			const date = getBestDate(properties) || "";
			const amount = properties.amount?.[0] as string | undefined;

			if (schema === "Event") {
				const keywords = (properties.keywords || []) as string[];
				if (keywords.some((k) => k.includes("Oral Evidence") || k.includes("Written Evidence"))) {
					type = "Evidence";
				} else if (keywords.some((k) => k.includes("Meeting"))) {
					type = "Meeting";
				} else if (properties.country && properties.country.length > 0) {
					type = "Visit";
				}
			} else if (schema === "Trip") {
				type = "Trip";
			} else if (schema === "Representation") {
				title = (properties.role?.[0] as string) || item.caption;
			} else if (schema === "Payment") {
				const purpose = (properties.purpose?.[0] as string | undefined) || "";
				const summary = (properties.summary?.[0] as string | undefined) || "";
				const purposeLower = purpose.toLowerCase();
				const summaryLower = summary.toLowerCase();
				if (purposeLower.includes("gift") || summaryLower.includes("gift")) {
					type = "Gift";
				} else if (
					purposeLower.includes("donation") ||
					summaryLower.includes("donation") ||
					summaryLower.includes("support")
				) {
					type = "Donation";
				}
			} else if (schema === "Ownership") {
				const asset = properties.asset?.[0] as { schema?: string } | undefined;
				if (asset?.schema === "Asset") type = "Property";
			} else if (schema === "Family") {
				const relationship = properties.relationship?.[0] as string | undefined;
				title = relationship || "Family member";
			} else if (schema === "UnknownLink") {
				// keep as-is
			} else if (schema === "PublicDisclosure") {
				// keep as-is
			} else if (schema === "Directorship") {
				// keep as-is
			} else {
				continue;
			}

			items.push({
				id: item.id,
				type,
				title,
				description,
				date,
				amount,
				properties,
				schema: item.schema,
				datasets: item.datasets,
			});
		}
	}

	return items.sort((a, b) => b.date.localeCompare(a.date));
}

export function transformRelationships(entity: Entity): RelationshipGroup[] {
	if (!entity.adjacent) return [];

	const currentId = entity.id;

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
			const datasetNames = Array.from(new Set(chain.flatMap((period) => period.datasetNames || [])));
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
			if (!item.id) continue;
			const key = [item.id, item.schema, item.role || ""].join("|");
			const periodStart = toDateToken(item.startDate);
			const periodEnd = toDateToken(item.endDate);
			const period: RelationshipPeriod | undefined =
				periodStart || periodEnd
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
			item.activePeriod = (item.periods || [])
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
		"other links": [],
	};

	for (const group of Object.values(entity.adjacent) as AdjacentGroup[]) {
		for (const item of group.results) {
			const schema = item.schema;
			const props = item.properties;
			const datasetNames = toDatasetNames(item.datasets);

			if (schema === "Employment") {
				const employees = (props.employee || []) as Array<Record<string, unknown>>;
				const employers = (props.employer || []) as Array<Record<string, unknown>>;

				if (employees.some((e) => e.id === currentId)) {
					for (const employer of employers) {
						const id = String(employer.id || "");
						if (!id) continue;
						groups.employers.push({
							id,
							statementId: item.id,
							name: String(employer.caption || ""),
							schema: String(employer.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}

				if (employers.some((e) => e.id === currentId)) {
					for (const employee of employees) {
						const id = String(employee.id || "");
						if (!id) continue;
						groups.employees.push({
							id,
							statementId: item.id,
							name: String(employee.caption || ""),
							schema: String(employee.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}
				continue;
			}

			if (schema === "Membership") {
				const members = (props.member || []) as Array<Record<string, unknown>>;
				const organizations = (props.organization || []) as Array<Record<string, unknown>>;

				if (members.some((m) => m.id === currentId)) {
					for (const organization of organizations) {
						const id = String(organization.id || "");
						if (!id) continue;
						groups.organizations.push({
							id,
							statementId: item.id,
							name: String(organization.caption || ""),
							schema: String(organization.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}

				if (organizations.some((o) => o.id === currentId)) {
					for (const member of members) {
						const id = String(member.id || "");
						if (!id) continue;
						groups.members.push({
							id,
							statementId: item.id,
							name: String(member.caption || ""),
							schema: String(member.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}
				continue;
			}

			if (schema === "Representation") {
				const agents = (props.agent || []) as Array<Record<string, unknown>>;
				const clients = (props.client || []) as Array<Record<string, unknown>>;

				if (clients.some((c) => c.id === currentId)) {
					for (const agent of agents) {
						const id = String(agent.id || "");
						if (!id) continue;
						groups.lobbyists.push({
							id,
							statementId: item.id,
							name: String(agent.caption || ""),
							schema: String(agent.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}

				if (agents.some((a) => a.id === currentId)) {
					for (const client of clients) {
						const id = String(client.id || "");
						if (!id) continue;
						groups.clients.push({
							id,
							statementId: item.id,
							name: String(client.caption || ""),
							schema: String(client.schema || "Entity"),
							role: props.role?.[0] as string | undefined,
							startDate: props.startDate?.[0] as string | undefined,
							endDate: props.endDate?.[0] as string | undefined,
							datasetNames,
						});
					}
				}
				continue;
			}

			if (schema === "UnknownLink") {
				const subjects = (props.subject || []) as Array<Record<string, unknown>>;
				const objects = (props.object || []) as Array<Record<string, unknown>>;
				const isSubject = subjects.some((s) => s.id === currentId);
				const isObject = objects.some((o) => o.id === currentId);
				if (!isSubject && !isObject) continue;

				const others = isSubject ? objects : subjects;
				for (const other of others) {
					const id = String(other.id || "");
					if (!id || id === currentId) continue;
					groups["other links"].push({
						id,
						statementId: item.id,
						name: String(other.caption || ""),
						schema: String(other.schema || "Entity"),
						datasetNames,
					});
				}
			}
		}
	}

	return Object.entries(groups)
		.filter(([, items]) => items.length > 0)
		.map(([type, items]) => ({ type, items: groupRelationshipItems(items) }));
}
