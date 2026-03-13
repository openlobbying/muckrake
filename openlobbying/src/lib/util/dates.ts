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

/**
 * Format a date as a quarter (e.g., "Q1 2024")
 */
export function formatQuarterDate(dateStr: string): string {
	try {
		const date = new Date(dateStr);
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

		const startParsed = startDate ? new Date(startDate) : undefined;
		const endParsed = endDate ? new Date(endDate) : undefined;
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
		const date = new Date(dateStr);
		if (Number.isNaN(date.getTime())) return dateStr;
		const day = date.getDate();
		const month = date.toLocaleDateString('en-GB', { month: 'long' });
		const year = date.getFullYear();
		return `${day} ${month} ${year}`;
	} catch {
		return dateStr;
	}
}
