export interface Entity {
    id: string;
    caption: string;
    schema: string;
    properties: Record<string, any[]>;
    datasets?: DatasetMetadata[];
    canonical_id?: string;
    adjacent?: Record<string, {
        results: Entity[];
        total: number;
    }>;
}

export interface DatasetMetadata {
    name: string;
    prefix?: string;
    title: string;
    summary?: string;
    tags?: string[];
    publisher?: {
        name?: string;
        description?: string;
        url?: string;
        country?: string;
        country_label?: string;
        official?: boolean;
    };
    url?: string;
	index_url?: string;
	licence?: {
		name?: string;
		url?: string;
	};
	coverage?: {
		countries?: string[];
		frequency?: string;
	};
}

export interface GraphNode {
    id: string;
    caption: string;
    schema: string;
}

export interface GraphEdge {
    from: string;
    to: string;
    label: string;
}

export interface GraphData {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

export interface TimelineItem {
    id: string;
    type: string;
    title: string;
    description: string;
    date: string;
    amount?: string;
    properties: Record<string, any[]>;
    schema: string;
	datasets?: DatasetMetadata[];
}

export interface RelationshipItem {
    id: string;
    statementId?: string;
    name: string;
    schema: string;
    role?: string;
    activePeriod?: string;
    startDate?: string;
    endDate?: string;
    datasetNames?: string[];
    periods?: RelationshipPeriod[];
}

export interface RelationshipPeriod {
	label: string;
	statementId?: string;
	statementIds?: string[];
	startDate?: string;
	endDate?: string;
	datasetNames?: string[];
}

export interface RelationshipGroup {
    type: string;
    items: RelationshipItem[];
}

export interface SearchResult {
	id: string;
	name: string;
	type: string;
}

export interface SearchResponse {
	results: SearchResult[];
	total: number;
	offset: number;
	limit: number;
	has_next: boolean;
	schema: string[];
	requested_schema?: string[];
	applied_schema?: string[];
}

export interface HomeStats {
	organizations: number;
	individuals: number;
	public_bodies: number;
	datasets: number;
	total_actors: number;
	by_schema: Record<string, number>;
	top_lobbying_companies: RankedActor[];
	top_organizations: RankedActor[];
}

export interface RankedActor {
	id: string;
	name: string;
	schema: string;
	connections: number;
}
