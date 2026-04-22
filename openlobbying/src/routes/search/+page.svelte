<script lang="ts">
	import { getEntityRoute } from '$lib/util/routes';
	import { Search } from '@lucide/svelte';
	import type { SearchResponse } from '$lib/types';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardHeader,
		CardTitle,
		CardDescription
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { Badge } from '$lib/components/ui/badge';

	interface SearchPageData {
		query: string;
		page: number;
		type: string | null;
		search: Promise<SearchResponse>;
	}

	let { data }: { data: SearchPageData } = $props();

	type TopLevelFilter = 'all' | 'organizations' | 'individuals';
	type OrganizationSubtype = 'all' | 'companies' | 'public-bodies';

	let selectedTopLevel = $state<TopLevelFilter>('all');
	let selectedOrganizationSubtype = $state<OrganizationSubtype>('all');

	$effect(() => {
		if (data.type === 'Person') {
			selectedTopLevel = 'individuals';
			selectedOrganizationSubtype = 'all';
			return;
		}
		if (data.type === 'Company') {
			selectedTopLevel = 'organizations';
			selectedOrganizationSubtype = 'companies';
			return;
		}
		if (data.type === 'PublicBody') {
			selectedTopLevel = 'organizations';
			selectedOrganizationSubtype = 'public-bodies';
			return;
		}
		if (data.type === 'Organization') {
			selectedTopLevel = 'organizations';
			selectedOrganizationSubtype = 'all';
			return;
		}
		selectedTopLevel = 'all';
		selectedOrganizationSubtype = 'all';
	});

	let selectedSchema = $derived.by(() => {
		if (selectedTopLevel === 'individuals') {
			return 'Person';
		}
		if (selectedTopLevel === 'organizations') {
			if (selectedOrganizationSubtype === 'companies') {
				return 'Company';
			}
			if (selectedOrganizationSubtype === 'public-bodies') {
				return 'PublicBody';
			}
			return 'Organization';
		}
		return '';
	});

	let currentPage = $derived(data.page ?? 1);

	function totalPagesFor(search: SearchResponse): number {
		return Math.max(1, Math.ceil((search.total || 0) / (search.limit || 20)));
	}

	function paginationHref(page: number): string {
		const params = new URLSearchParams();
		if (data.query) {
			params.set('q', data.query);
		}
		if (page > 1) {
			params.set('page', String(page));
		}
		if (data.type) {
			params.set('type', data.type);
		}
		const q = params.toString();
		return q ? `/search?${q}` : '/search';
	}

	function setTopLevel(filter: TopLevelFilter): void {
		selectedTopLevel = filter;
		if (filter !== 'organizations') {
			selectedOrganizationSubtype = 'all';
		}
	}
</script>

<svelte:head>
	<title>Search - OpenLobbying</title>
	<meta
		name="description"
		content="Search organisations, individuals, and public bodies across OpenLobbying datasets."
	/>
	<meta name="robots" content="noindex,follow" />
</svelte:head>

<div class="mx-auto max-w-6xl overflow-x-hidden px-4 py-12">
	<header class="mb-8">
		<h1 class="text-4xl font-semibold tracking-tight text-slate-900">Search OpenLobbying</h1>
		<p class="mt-3 max-w-3xl text-slate-600">
			Search by organisation name, individual name, public body, or known identifier.
		</p>
	</header>

	<Card class="mb-8 rounded-2xl py-0 gap-0">
		<CardContent class="p-4 sm:p-6">
		<form action="/search" method="GET" class="space-y-4">
			<div class="grid gap-3 md:grid-cols-[1fr_120px]">
				<label class="relative block">
					<span class="sr-only">Search query</span>
					<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center">
						<Search class="h-5 w-5 text-slate-400" />
					</span>
					<Input
						type="text"
						name="q"
						value={data.query ?? ''}
						placeholder="Try: Palantir, Arden Strategies, Keir Starmer, Department for Energy Security and Net Zero..."
						class="h-12 rounded-xl bg-white py-3 pl-11 pr-3 text-base"
					/>
				</label>

				<Button type="submit" class="h-12 rounded-xl px-4">Search</Button>
			</div>

			<input type="hidden" name="type" value={selectedSchema} />

			<div class="space-y-2">
				<div class="flex flex-wrap gap-2">
					<Button
						type="button"
						variant={selectedTopLevel === 'all' ? 'default' : 'outline'}
						onclick={() => setTopLevel('all')}
					>
						All entities
					</Button>
					<Button
						type="button"
						variant={selectedTopLevel === 'organizations' ? 'default' : 'outline'}
						onclick={() => setTopLevel('organizations')}
					>
						Organisations
					</Button>
					<Button
						type="button"
						variant={selectedTopLevel === 'individuals' ? 'default' : 'outline'}
						onclick={() => setTopLevel('individuals')}
					>
						Individuals
					</Button>
				</div>

				{#if selectedTopLevel === 'organizations'}
					<div class="flex flex-wrap gap-2 pl-2">
						<Button
							type="button"
							size="sm"
							variant={selectedOrganizationSubtype === 'all' ? 'default' : 'outline'}
							onclick={() => (selectedOrganizationSubtype = 'all')}
						>
							All organisations
						</Button>
						<Button
							type="button"
							size="sm"
							variant={selectedOrganizationSubtype === 'companies' ? 'default' : 'outline'}
							onclick={() => (selectedOrganizationSubtype = 'companies')}
						>
							Companies
						</Button>
						<Button
							type="button"
							size="sm"
							variant={selectedOrganizationSubtype === 'public-bodies' ? 'default' : 'outline'}
							onclick={() => (selectedOrganizationSubtype = 'public-bodies')}
						>
							Public bodies
						</Button>
					</div>
				{/if}
			</div>
		</form>
		</CardContent>
	</Card>

	{#if data.query}
		{#await data.search}
			<section class="space-y-4">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<Skeleton class="h-6 w-56 rounded" />
					<Skeleton class="h-4 w-28 rounded" />
				</div>

				<div class="grid gap-3">
					{#each Array.from({ length: 6 }) as _}
						<Card class="overflow-hidden py-0 gap-0">
							<CardContent class="space-y-2 p-5">
								<div class="flex items-center gap-2">
									<Skeleton class="h-6 w-64 rounded" />
									<Skeleton class="h-5 w-24 rounded-full" />
								</div>
								<Skeleton class="h-4 w-full rounded" />
							</CardContent>
						</Card>
					{/each}
				</div>

				<Card class="mt-6 py-0 gap-0">
					<CardContent class="flex items-center justify-between gap-4 p-4">
						<Skeleton class="h-10 w-24 rounded-xl" />
						<Skeleton class="h-4 w-24 rounded" />
						<Skeleton class="h-10 w-20 rounded-xl" />
					</CardContent>
				</Card>
			</section>
		{:then search}
			{@const totalPages = totalPagesFor(search)}
			<section class="space-y-4">
				<div class="flex flex-wrap items-baseline justify-between gap-2">
					<h2 class="min-w-0 break-words text-lg font-semibold text-slate-900">
						{search.total} result{search.total === 1 ? '' : 's'} for "{data.query}"
					</h2>
					<p class="text-sm text-slate-500">Page {currentPage} of {totalPages}</p>
				</div>

				<div class="grid gap-3">
					{#each search.results as result}
						<Card class="overflow-hidden py-0 gap-0 transition hover:border-blue-300 hover:shadow">
							<CardContent class="p-5">
								<a href={getEntityRoute(result.id, result.type)} class="group block">
									<div class="flex items-start justify-between gap-3">
										<div class="min-w-0">
											<div class="mb-1 flex flex-wrap items-center gap-2">
												<h3 class="break-words text-lg font-semibold text-slate-900 group-hover:text-blue-700">
													{result.name}
												</h3>
												<Badge variant="secondary">{result.type}</Badge>
											</div>
											<p class="break-all font-mono text-xs text-slate-500">{result.id}</p>
										</div>
									</div>
								</a>
							</CardContent>
						</Card>
					{:else}
						<Card class="rounded-2xl">
							<CardHeader>
								<CardTitle>No results found</CardTitle>
								<CardDescription>How to search effectively</CardDescription>
							</CardHeader>
							<CardContent>
								<p class="mb-4 text-slate-600">Try a shorter query or remove filters.</p>
								<ul class="space-y-2 text-slate-600">
									<li>Use simple search terms</li>
									<li>Don't include suffixes such as Ltd, Plc and honorifics</li>
									<li>Use type filters to narrow down crowded results</li>
								</ul>
							</CardContent>
						</Card>
					{/each}
				</div>

				{#if search.total > search.limit}
					<Card class="mt-6 py-0 gap-0">
						<CardContent class="flex items-center justify-between gap-4 p-4">
						{#if currentPage > 1}
							<Button href={paginationHref(currentPage - 1)} variant="outline">Previous</Button>
						{:else}
							<Button variant="outline" disabled>Previous</Button>
						{/if}

						<span class="text-sm text-slate-600">Page {currentPage} of {totalPages}</span>

						{#if currentPage < totalPages}
							<Button href={paginationHref(currentPage + 1)} variant="outline">Next</Button>
						{:else}
							<Button variant="outline" disabled>Next</Button>
						{/if}
						</CardContent>
					</Card>
				{/if}
			</section>
		{:catch}
			<Card>
				<CardContent class="p-8 text-center text-slate-600">
					Could not fetch search results. Please try again.
				</CardContent>
			</Card>
		{/await}
	{/if}
</div>
