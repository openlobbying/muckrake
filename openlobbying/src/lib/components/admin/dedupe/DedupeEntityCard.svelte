<script lang="ts">
	import DatasetList from '$lib/components/DatasetList.svelte';
	import Properties from '$lib/components/Properties.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import type { Entity } from '$lib/types';
	import { getEntityRoute } from '$lib/util/routes';

	interface Props {
		entity: Entity;
		score?: number | null;
		selectable?: boolean;
		selected?: boolean;
		checkboxName?: string;
		checkboxLabel?: string;
	}

	let {
		entity,
		score = null,
		selectable = false,
		selected = false,
		checkboxName = 'selectedId',
		checkboxLabel = 'Include this record'
	}: Props = $props();

	let href = $derived(getEntityRoute(entity.id, entity.schema));
	let name = $derived(String(entity.properties.name?.[0] ?? entity.caption ?? entity.id));
</script>

<Card class="h-full border-slate-200 bg-white shadow-sm">
	<CardHeader class="space-y-4">
		<div class="flex items-start justify-between gap-3">
			{#if selectable}
				<label class="flex items-start gap-3 text-sm text-slate-700">
					<input
						type="checkbox"
						name={checkboxName}
						value={entity.id}
						checked={selected}
						class="mt-1 h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
					/>
					<span>
						<span class="block text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
							{checkboxLabel}
						</span>
						<span class="mt-1 block font-mono text-xs text-slate-500">{entity.id}</span>
					</span>
				</label>
			{:else}
				<div class="space-y-1">
					<CardTitle class="text-xl text-slate-900">{name}</CardTitle>
					<CardDescription class="font-mono text-xs text-slate-500">{entity.id}</CardDescription>
				</div>
			{/if}
			<Badge variant="secondary">{entity.schema}</Badge>
		</div>

		{#if selectable}
			<div class="space-y-1">
				<CardTitle class="text-xl text-slate-900">{name}</CardTitle>
				{#if score !== null && score !== undefined}
					<CardDescription>Best linked score: {score.toFixed(3)}</CardDescription>
				{/if}
			</div>
		{/if}

		{#if entity.datasets && entity.datasets.length > 0}
			<DatasetList datasets={entity.datasets} variant="badges" />
		{/if}

		<a href={href} class="text-sm font-medium text-slate-700 underline underline-offset-4 hover:text-slate-950">
			Open full record
		</a>
	</CardHeader>
	<CardContent>
		<Properties properties={entity.properties} type={entity.schema} />
	</CardContent>
</Card>
