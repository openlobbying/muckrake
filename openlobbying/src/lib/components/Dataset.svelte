<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '$lib/components/ui/card';
	import type { DatasetMetadata } from '$lib/types';

	let { dataset }: { dataset: DatasetMetadata } = $props();
</script>

<Card class="h-full gap-0">
	<CardHeader>
		<CardTitle>
			{#if dataset.url}
				<a
					href={dataset.url}
					class="hover:text-blue-600 hover:underline"
					target="_blank"
					rel="noopener noreferrer"
				>
					{dataset.title}
				</a>
			{:else}
				{dataset.title}
			{/if}
		</CardTitle>
	</CardHeader>
	<CardContent class="flex h-full flex-col">
		{#if dataset.name}
			<p class="mb-2 font-mono text-xs text-slate-500">{dataset.name}</p>
		{/if}

		{#if dataset.publisher?.name}
			<CardDescription class="mb-3">
				Published by
				{#if dataset.publisher.url}
					<a
						href={dataset.publisher.url}
						class="text-blue-600 hover:underline"
						target="_blank"
						rel="noopener noreferrer"
					>
						{dataset.publisher.name}
					</a>
				{:else}
					{dataset.publisher.name}
				{/if}
			</CardDescription>
		{/if}

		{#if dataset.summary}
			<p class="mb-4 flex-grow overflow-hidden text-sm text-gray-700">
				{dataset.summary}
			</p>
		{/if}

		{#if dataset.licence?.name}
			<CardDescription class="mt-auto">
				Licence:
				{#if dataset.licence.url}
					<a
						href={dataset.licence.url}
						class="text-blue-600 hover:underline"
						target="_blank"
						rel="noopener noreferrer"
					>
						{dataset.licence.name}
					</a>
				{:else}
					{dataset.licence.name}
				{/if}
			</CardDescription>
		{/if}
	</CardContent>
</Card>
