export function getMuckrakeApiBaseUrl(): string {
	return process.env.MUCKRAKE_API_URL || 'http://127.0.0.1:8000';
}
