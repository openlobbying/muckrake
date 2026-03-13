<script lang="ts">
	import { getKeyDetails } from "$lib/util/entity_config";
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';

	let { entity } = $props();

	const details = $derived(getKeyDetails(entity));
</script>

{#if details.length > 0}
	<Card>
		<CardHeader>
			<CardTitle>Key Details</CardTitle>
		</CardHeader>
		<CardContent>
		<div class="space-y-4">
			{#each details as detail (detail.label)}
				<div class="flex items-start space-x-3">
					<detail.icon
						class="w-5 h-5 text-gray-400 flex-shrink-0 mt-0.5"
					/>
					<div class="min-w-0 flex-1">
						<p class="text-sm font-medium text-gray-600">
							{detail.label}
						</p>
						<div class="space-y-1 mt-0.5">
							{#each detail.values as value, i (value + i)}
								{#if detail.linkUrl}
									<a
										href={detail.linkUrl}
										target="_blank"
										rel="noopener noreferrer"
										class="block text-sm text-blue-600 hover:text-blue-700 break-all"
									>
										{value}
									</a>
								{:else if detail.isLink}
									<a
										href={value}
										target="_blank"
										rel="noopener noreferrer"
										class="block text-sm text-blue-600 hover:text-blue-700 break-all"
									>
										{value}
									</a>
								{:else}
									<p
										class="text-sm text-gray-900 break-words"
									>
										{value}
									</p>
								{/if}
							{/each}
						</div>
					</div>
				</div>
			{/each}
		</div>
		</CardContent>
	</Card>
{/if}
