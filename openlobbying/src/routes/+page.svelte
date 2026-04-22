<script lang="ts">
	import type { HomeStats } from '$lib/types';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import * as Table from '$lib/components/ui/table/index.js';
	import { Input } from '$lib/components/ui/input';

	interface HomePageData {
		stats: HomeStats;
	}

	let { data }: { data: HomePageData } = $props();
	let stats = $derived(data.stats);
	const siteUrl = 'https://openlobbying.org';
	const pageTitle = 'OpenLobbying | UK lobbying data explorer';
	const pageDescription =
		'Search UK lobbying organisations, individuals and public bodies, with linked source datasets and relationship data.';
	const homeStructuredData = JSON.stringify({
		'@context': 'https://schema.org',
		'@type': 'WebSite',
		name: 'OpenLobbying',
		url: siteUrl,
		description: pageDescription,
		publisher: {
			'@type': 'Organization',
			name: 'OpenLobbying',
			url: siteUrl
		},
		potentialAction: {
			'@type': 'SearchAction',
			target: `${siteUrl}/search?q={search_term_string}`,
			'query-input': 'required name=search_term_string'
		}
	});

	function formatNumber(value: number): string {
		return new Intl.NumberFormat('en-GB').format(value);
	}
</script>

<svelte:head>
	<title>{pageTitle}</title>
	<meta name="description" content={pageDescription} />
	<meta property="og:title" content={pageTitle} />
	<meta property="og:description" content={pageDescription} />
	<meta property="og:url" content={siteUrl} />
	<meta name="twitter:title" content={pageTitle} />
	<meta name="twitter:description" content={pageDescription} />
	<script type="application/ld+json">{homeStructuredData}</script>
</svelte:head>

<div class="bg-gradient-to-b from-amber-50 via-slate-50 to-white">
	<section class="w-full px-4 pb-12 pt-14 sm:px-6 lg:px-10">
		<div class="mx-auto max-w-6xl rounded-3xl border border-amber-100 bg-gradient-to-r from-white via-amber-50/70 to-slate-50 p-6 shadow-sm sm:p-8 lg:p-10">
			<div class="mx-auto max-w-3xl">
				<p class="inline-flex items-center rounded-full border border-amber-200 bg-amber-100 px-3 py-1 text-xs font-medium uppercase tracking-wide text-amber-800">
					Open data
				</p>
			</div>
			<h1 class="mx-auto mt-4 max-w-3xl text-4xl font-semibold tracking-tight text-slate-900 sm:text-5xl">
				Understand who influences policy in the UK
			</h1>
			<p class="mx-auto mt-4 max-w-3xl text-lg text-slate-600">
				OpenLobbying collects, cleans and standardises lobbying registers so you can explore how corporations shape policy.
			</p>

			<form action="/search" method="GET" class="mx-auto mt-8 max-w-3xl">
				<Card class="gap-0 rounded-2xl border-amber-100/70 bg-white/90 py-0 shadow-sm backdrop-blur">
					<CardContent class="p-3">
						<div class="flex flex-col gap-3 sm:flex-row sm:items-center">
							<Input
								type="text"
								name="q"
								autocomplete="off"
								placeholder="Try: Palantir, Arden Strategies, Keir Starmer, Department for Energy Security and Net Zero..."
								class="h-12 rounded-xl px-4 text-base"
							/>
							<Button type="submit" class="h-12 shrink-0 rounded-xl px-5">
								Search
							</Button>
						</div>
					</CardContent>
				</Card>
			</form>
		</div>
	</section>

	<section class="mx-auto max-w-6xl px-4 pb-12">
		<div class="grid gap-6 lg:grid-cols-2">
			<Card class="rounded-2xl">
				<CardHeader>
					<CardTitle>What's included</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="grid grid-cols-2 gap-3">
						<div class="rounded-xl bg-slate-50 p-4">
							<p class="text-2xl font-semibold text-slate-900">{formatNumber(stats.organizations)}</p>
							<p class="text-sm text-slate-500">Organisations</p>
						</div>
						<div class="rounded-xl bg-slate-50 p-4">
							<p class="text-2xl font-semibold text-slate-900">{formatNumber(stats.individuals)}</p>
							<p class="text-sm text-slate-500">Individuals</p>
						</div>
						<div class="rounded-xl bg-slate-50 p-4">
							<p class="text-2xl font-semibold text-slate-900">{formatNumber(stats.public_bodies)}</p>
							<p class="text-sm text-slate-500">Public bodies</p>
						</div>
						<div class="rounded-xl bg-slate-50 p-4">
							<p class="text-2xl font-semibold text-slate-900">{formatNumber(stats.datasets)}</p>
							<p class="text-sm text-slate-500">Data sources</p>
						</div>
					</div>
				</CardContent>
			</Card>

			<Card class="rounded-2xl">
				<CardHeader>
					<CardTitle>What's missing</CardTitle>
				</CardHeader>
				<CardContent>
					<ul class="space-y-2 text-slate-600">
					<li>In this alpha version, the data is limited to 2025-2026. It is incomplete even for those years.</li>
					<li>You will see many duplicate and messy results, those will be resolved in the future.</li>
					<li>We plan to include additional data sources in coming months.</li>
					</ul>
					<Button href="/datasets" variant="outline" class="mt-5">Browse datasets</Button>
				</CardContent>
			</Card>
		</div>

		<div class="mt-6 grid gap-6 lg:grid-cols-2">
			<Card class="rounded-2xl">
				<CardHeader>
					<CardTitle>Top lobbying companies</CardTitle>
					<!-- <CardDescription>Ranked by number of linked connections</CardDescription> -->
				</CardHeader>
				<CardContent>
					<Table.Root class="table-fixed">
						<Table.Header>
							<Table.Row>
								<Table.Head class="w-full">Company</Table.Head>
								<Table.Head class="w-24 whitespace-nowrap text-right">Connections</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each stats.top_lobbying_companies as row}
								<Table.Row>
									<Table.Cell class="whitespace-normal break-words align-top">
										<a href={`/profile/${row.id}`} class="block break-words text-blue-700 hover:underline">
											{row.name}
										</a>
									</Table.Cell>
									<Table.Cell class="whitespace-nowrap text-right font-medium">{formatNumber(row.connections)}</Table.Cell>
								</Table.Row>
							{:else}
								<Table.Row>
									<Table.Cell colspan={2} class="text-center text-slate-500">No ranking data yet.</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</CardContent>
			</Card>

			<Card class="rounded-2xl">
				<CardHeader>
					<CardTitle>Top organisations</CardTitle>
					<!-- <CardDescription>Most connected organisation</CardDescription> -->
				</CardHeader>
				<CardContent>
					<Table.Root class="table-fixed">
						<Table.Header>
							<Table.Row>
								<Table.Head class="w-full">Organisation</Table.Head>
								<Table.Head class="w-24 whitespace-nowrap text-right">Connections</Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each stats.top_organizations as row}
								<Table.Row>
									<Table.Cell class="whitespace-normal break-words align-top">
										<a href={`/profile/${row.id}`} class="block break-words text-blue-700 hover:underline">
											{row.name}
										</a>
									</Table.Cell>
									<Table.Cell class="whitespace-nowrap text-right font-medium">{formatNumber(row.connections)}</Table.Cell>
								</Table.Row>
							{:else}
								<Table.Row>
									<Table.Cell colspan={2} class="text-center text-slate-500">No ranking data yet.</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				</CardContent>
			</Card>
		</div>
	</section>
</div>
