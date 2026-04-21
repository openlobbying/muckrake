<script lang="ts">
	import DatasetList from '$lib/components/DatasetList.svelte';
	import Properties from '$lib/components/Properties.svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { getStatementPropertyOrder } from '$lib/presentation/property-profile';

	let { data } = $props();
	let entity = $derived(data.entity);
	const orderedKeys = $derived(getStatementPropertyOrder(entity.schema, entity.properties));
</script>

<svelte:head>
	<title>{entity.caption ?? entity.canonical_id} - OpenLobbying</title>
</svelte:head>

<div class="max-w-4xl mx-auto px-4 py-8">
	<header class="mb-8 border-b border-gray-200 pb-6">
		<h1 class="text-3xl font-bold text-gray-900 mb-2">
			{entity.caption ?? entity.canonical_id}
		</h1>
		<div class="flex items-center gap-3">
			<Badge variant="secondary">{entity.schema}</Badge>
			<span class="text-sm text-gray-500 font-mono">{entity.canonical_id}</span>
		</div>
	</header>

	<Card class="mb-8">
		<CardHeader>
			<CardTitle>Properties</CardTitle>
		</CardHeader>
		<CardContent>
		<Properties properties={entity.properties} type={entity.schema} orderedKeys={orderedKeys} />
		</CardContent>
	</Card>

	{#if entity.datasets && entity.datasets.length > 0}
		<Card>
			<CardHeader>
				<CardTitle>Datasets</CardTitle>
			</CardHeader>
			<CardContent>
				<DatasetList datasets={entity.datasets} variant="badges" />
			</CardContent>
		</Card>
	{/if}
</div>
