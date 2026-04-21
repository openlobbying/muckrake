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
