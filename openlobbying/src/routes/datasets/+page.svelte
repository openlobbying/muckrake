<script lang="ts">
    import Dataset from "$lib/components/Dataset.svelte";
	import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '$lib/components/ui/card';

    let { data } = $props();
    let datasets = $derived(data.datasets);
</script>

<svelte:head>
    <title>Datasets - OpenLobbying</title>
</svelte:head>

<div class="max-w-7xl mx-auto px-4 py-8">
	<Card class="mb-8">
		<CardHeader>
			<CardTitle>Datasets</CardTitle>
			<CardDescription>The sources of data used in OpenLobbying.</CardDescription>
		</CardHeader>
	</Card>

	<Card class="mb-8 border-slate-200 bg-slate-50">
		<CardHeader>
			<CardTitle>Methodology and limitations</CardTitle>
			<CardDescription>
				How OpenLobbying collects, standardises, and links records across sources.
			</CardDescription>
		</CardHeader>
		<CardContent class="space-y-4 text-slate-700">
			<p>
				OpenLobbying republishes data from public sources and converts records into a common structure so
				entries from different datasets can be compared and explored together.
			</p>
			<ul class="list-disc space-y-1 pl-6">
				<li>We ingest records from official registers, parliamentary data, and transparency datasets.</li>
				<li>We normalise names, entities, and relationship data into one model.</li>
				<li>We use matching and deduplication algorithms to generate candidate links.</li>
				<li>All final entity links are reviewed and approved by a human before publication.</li>
				<li>Each profile can aggregate activity from multiple underlying sources.</li>
			</ul>
			<p>
				No profile is linked through a solely automated decision process. However, errors can still happen:
				source data can be incomplete, delayed, or inconsistent, and manual review can miss issues.
			</p>
			<p>
				Where available, records include a link to the original source publication so users can verify the
				underlying information directly.
			</p>
			<p>
				This project is designed for public-interest journalism, research, and long-term archival value.
			</p>
			<p>
				Use OpenLobbying as a research aid, not as the sole basis for factual conclusions. For publication,
				we recommend verifying key facts against primary source records.
			</p>
		</CardContent>
	</Card>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {#each datasets as dataset}
            <Dataset {dataset} />
        {/each}
    </div>
</div>
