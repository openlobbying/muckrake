const MONTH_TOKEN = /^\d{4}-\d{2}$/;
const DATE_TOKEN = /^\d{4}-\d{2}-\d{2}$/;

export function getBestDate(props: Record<string, any[]>): string | undefined {
	const dateProps = [
		'date',
		'startDate',
		'endDate',
		'incorporationDate',
		'registrationDate',
		'created_at',
		'publishedAt'
	];
	
	for (const prop of dateProps) {
		if (props[prop] && props[prop].length > 0) {
			return props[prop][0] as string;
		}
	}
	return undefined;
}

export function isDateToken(value: unknown): value is string {
	return typeof value === 'string' && (MONTH_TOKEN.test(value) || DATE_TOKEN.test(value));
}

export function toDateBoundary(value: string, end = false): Date | undefined {
	if (MONTH_TOKEN.test(value)) {
		const [year, month] = value.split('-').map(Number);
		const day = end ? new Date(Date.UTC(year, month, 0)).getUTCDate() : 1;
		return new Date(Date.UTC(year, month - 1, day));
	}

	if (DATE_TOKEN.test(value)) {
		return new Date(`${value}T00:00:00Z`);
	}

	return undefined;
}

export function formatDateToken(value?: string): string | undefined {
	if (!value) return undefined;

	const date = toDateBoundary(value);
	if (!date) return value;

	if (MONTH_TOKEN.test(value)) {
		return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
	}

	return date.toLocaleDateString('en-GB', {
		day: 'numeric',
		month: 'short',
		year: 'numeric',
		timeZone: 'UTC'
	});
}

/**
 * Format a date as a quarter (e.g., "Q1 2024")
 */
export function formatQuarterDate(dateStr: string): string {
	try {
		const date = toDateBoundary(dateStr) || new Date(dateStr);
		if (Number.isNaN(date.getTime())) return dateStr;
		const year = date.getFullYear();
		const month = date.getMonth(); // 0-11
		const quarter = Math.floor(month / 3) + 1;
		return `Q${quarter} ${year}`;
	} catch {
		return dateStr;
	}
}

export function formatQuarterRange(startDate?: string, endDate?: string): string {
	const start = startDate ? formatQuarterDate(startDate) : undefined;
	const end = endDate ? formatQuarterDate(endDate) : undefined;

	if (start && end) {
		if (start === end) return start;

		const startParsed = startDate ? toDateBoundary(startDate) : undefined;
		const endParsed = endDate ? toDateBoundary(endDate, true) : undefined;
		if (
			startParsed &&
			endParsed &&
			!Number.isNaN(startParsed.getTime()) &&
			!Number.isNaN(endParsed.getTime()) &&
			startParsed.getFullYear() === endParsed.getFullYear()
		) {
			const startQuarter = Math.floor(startParsed.getMonth() / 3) + 1;
			const endQuarter = Math.floor(endParsed.getMonth() / 3) + 1;
			return `Q${startQuarter} - Q${endQuarter} ${startParsed.getFullYear()}`;
		}

		return `${start} - ${end}`;
	}
	if (start) return start;
	if (end) return end;
	return 'Unknown Date';
}

/**
 * Format a date in full format (e.g., "1 January 2024")
 */
export function formatFullDate(dateStr: string): string {
	try {
		const date = toDateBoundary(dateStr) || new Date(dateStr);
		if (Number.isNaN(date.getTime())) return dateStr;
		if (MONTH_TOKEN.test(dateStr)) {
			return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' });
		}
		const day = date.getDate();
		const month = date.toLocaleDateString('en-GB', { month: 'long', timeZone: 'UTC' });
		const year = date.getFullYear();
		return `${day} ${month} ${year}`;
	} catch {
		return dateStr;
	}
}

export function formatDateRange(startDate?: string, endDate?: string): string {
	const start = formatDateToken(startDate);
	const end = formatDateToken(endDate);
	if (start && end && start === end) return start;
	if (start && end) return `${start} - ${end}`;
	if (start) return start;
	if (end) return end;
	return 'Unknown Date';
}
