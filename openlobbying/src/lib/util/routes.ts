const ACTOR_SCHEMATA = new Set([
    'Person', 'Company', 'Organization', 'PublicBody', 'LegalEntity'
]);

export function getEntityRoute(id: string, schema: string): string {
	if (ACTOR_SCHEMATA.has(schema)) {
		return `/profile/${id}`;
	}
	// Default to statement view for everything else (Payments, Relationships, etc.)
	return `/statement/${id}`;
}

export function getApiEndpoint(id: string, schema: string): string {
    if (ACTOR_SCHEMATA.has(schema)) {
        return `/api/profiles/${id}`;
    }
    return `/api/statements/${id}`;
}
