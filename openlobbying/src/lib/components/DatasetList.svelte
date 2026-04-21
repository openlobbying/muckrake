<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import type { DatasetMetadata } from '$lib/types';

	type DatasetListVariant = 'badges' | 'inline' | 'stacked';

	interface Props {
		datasets?: DatasetMetadata[];
		variant?: DatasetListVariant;
	}

	let { datasets = [], variant = 'badges' }: Props = $props();

	const labels = $derived(
		datasets
			.map((dataset) => dataset.title || dataset.name)
			.filter((label): label is string => Boolean(label))
	);
</script>

{#if labels.length > 0}
	{#if variant === 'inline'}
		<p class="text-sm text-gray-700">
			<span class="text-gray-500">Datasets:</span>
			{#each labels as label, i}
				{#if i > 0}, {/if}
				{label}
			{/each}
		</p>
	{:else if variant === 'stacked'}
		<div class="space-y-2">
			{#each labels as label (label)}
				<div class="border-b border-gray-100 pb-2 last:border-0 last:pb-0">
					<p class="text-sm text-gray-700">{label}</p>
				</div>
			{/each}
		</div>
	{:else}
		<div class="flex flex-wrap gap-2">
			{#each labels as label (label)}
				<Badge variant="secondary">{label}</Badge>
			{/each}
		</div>
	{/if}
{/if}
