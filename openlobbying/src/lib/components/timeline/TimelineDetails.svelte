<script lang="ts">
	import { getPropertyLabel, getTimelineDetailRows } from '$lib/presentation/property-profile';
	import {
		formatLabel,
		getDatasetLabel,
		renderableValue,
		type DetailRow
	} from '$lib/util/detail';

	interface Props {
		activity: any;
	}

	let { activity }: Props = $props();

	const detailRows = $derived<DetailRow[]>(getTimelineDetailRows(activity?.type || '', activity?.properties));
	const hasDatasets = $derived(Boolean(activity?.datasets && activity.datasets.length > 0));
	const hasContent = $derived(hasDatasets || detailRows.length > 0);
</script>

{#if hasContent}
	<div class="mt-3 border-t border-gray-100 pt-3">
		{#if hasDatasets}
			<p class="text-sm text-gray-700">
				<span class="text-gray-500">Datasets:</span>
				{#each activity.datasets as dataset, i}
					{#if i > 0}, {/if}
					{getDatasetLabel(dataset)}
				{/each}
			</p>
		{/if}

		{#if detailRows.length > 0}
			<div class="space-y-1.5 {hasDatasets ? 'mt-2' : ''}">
				{#each detailRows as row (row.key)}
					<p class="text-sm text-gray-700">
						<span class="text-gray-500">{formatLabel(getPropertyLabel(activity?.type || '', row.key))}:</span>
						{#each row.values as value, i}
							{#if i > 0}, {/if}
							{@const item = renderableValue(value, row.key)}
							{#if item.type === 'entity'}
								<a href={item.href} class="text-blue-600 hover:underline">{item.text}</a>
							{:else if item.type === 'url'}
								<a href={item.href} target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">
									{item.text}
								</a>
							{:else}
								{item.text}
							{/if}
						{/each}
					</p>
				{/each}
			</div>
		{/if}
	</div>
{:else}
	<div class="mt-3 border-t border-gray-100 pt-3">
		<p class="text-sm text-gray-500">No additional details available.</p>
	</div>
{/if}
