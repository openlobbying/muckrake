<script lang="ts">
	import Properties from '$lib/components/Properties.svelte';
	import Timeline from '$lib/components/timeline/Timeline.svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

	let { data } = $props();
	let entity = $derived(data.entity);

	function getBestDate(props: Record<string, any[]>): string | undefined {
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

	let timelineItems = $derived.by(() => {
		if (!entity.adjacent) return [];

		const items: any[] = [];
		for (const [relType, group] of Object.entries(entity.adjacent)) {
			// @ts-ignore
			for (const item of group.results) {
				items.push({
					id: item.id,
					type: item.schema,
					title: item.caption,
					date: getBestDate(item.properties),
					description:
						item.properties.role?.[0] ||
						item.properties.summary?.[0] ||
						relType,
					properties: item.properties
				});
			}
		}
		return items.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
	});
</script>

<svelte:head>
	<title>{entity.properties.name?.[0] ?? entity.caption ?? entity.canonical_id} - OpenLobbying</title>
</svelte:head>

<div class="mx-auto max-w-4xl px-4 py-8">
	<header class="mb-8 border-b border-gray-200 pb-6">
		<h1 class="mb-2 text-3xl font-bold text-gray-900">
			{entity.properties.name?.[0] ?? entity.caption ?? entity.canonical_id}
		</h1>
		<div class="flex items-center gap-3">
			<Badge variant="secondary">{entity.schema}</Badge>
			<span class="font-mono text-sm text-gray-500">{entity.canonical_id}</span>
		</div>
	</header>

	<Card class="mb-8">
		<CardHeader>
			<CardTitle>Properties</CardTitle>
		</CardHeader>
		<CardContent>
			<Properties properties={entity.properties} />
		</CardContent>
	</Card>

	{#if timelineItems.length > 0}
		<section class="mb-8">
			<Timeline activities={timelineItems} currentEntityId={entity.id} title="Timeline" />
		</section>
	{/if}

	{#if entity.datasets && entity.datasets.length > 0}
		<Card>
			<CardHeader>
				<CardTitle>Datasets</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="flex flex-wrap gap-2">
					{#each entity.datasets as dataset}
						<Badge variant="secondary">{dataset}</Badge>
					{/each}
				</div>
			</CardContent>
		</Card>
	{/if}
</div>
