<script lang="ts">
	import Properties from '$lib/components/Properties.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import type { Entity } from '$lib/types';
	import { getEntityDatasets, getEntityHref, getEntityName } from './utils';

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

	let datasetTitles = $derived(getEntityDatasets(entity));
	let href = $derived(getEntityHref(entity));
	let name = $derived(getEntityName(entity));
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

		{#if datasetTitles.length > 0}
			<div class="flex flex-wrap gap-2">
				{#each datasetTitles as title (title)}
					<Badge variant="secondary">{title}</Badge>
				{/each}
			</div>
		{/if}

		<a href={href} class="text-sm font-medium text-slate-700 underline underline-offset-4 hover:text-slate-950">
			Open full record
		</a>
	</CardHeader>
	<CardContent>
		<Properties properties={entity.properties} type={entity.schema} />
	</CardContent>
</Card>
