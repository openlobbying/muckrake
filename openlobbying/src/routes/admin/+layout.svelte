<script lang="ts">
	import { page } from '$app/state';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Separator } from '$lib/components/ui/separator';
	import { cn } from '$lib/utils';
	import type { Snippet } from 'svelte';

	interface Props {
		children?: Snippet;
	}

	let { children }: Props = $props();

	const navItems = [
		{ href: '/admin/users', label: 'Users', description: 'User accounts and roles' },
		{ href: '/admin/dedupe/pairs', label: 'Dedupe pairs', description: 'Pair-by-pair review queue' },
		{ href: '/admin/dedupe/clusters', label: 'Dedupe clusters', description: 'Grouped merge review' }
	];

	function isActiveRoute(href: string): boolean {
		const pathname = page.url.pathname;
		return pathname === href || pathname.startsWith(`${href}/`);
	}
</script>

<svelte:head>
	<meta name="robots" content="noindex,nofollow" />
</svelte:head>

<div class="px-4 py-10 sm:px-6">
	<div class="mx-auto max-w-7xl space-y-6">
		<div class="space-y-2">
			<p class="text-sm font-medium uppercase tracking-[0.2em] text-slate-500">Admin</p>
			<h1 class="text-3xl font-semibold tracking-tight text-slate-950">Internal tools</h1>
			<p class="max-w-3xl text-sm leading-6 text-slate-600">
				A single place for user management and resolver review.
			</p>
		</div>

		<div class="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
			<Card class="h-fit border-slate-200">
				<CardHeader class="pb-3">
					<CardTitle class="text-base">Tools</CardTitle>
				</CardHeader>
				<Separator />
				<CardContent class="p-3">
					<nav class="space-y-1" aria-label="Admin navigation">
						{#each navItems as item (item.href)}
							<a
								href={item.href}
								class={cn(
									'block rounded-md px-3 py-2 transition-colors',
									isActiveRoute(item.href)
										? 'bg-slate-900 text-white'
										: 'text-slate-700 hover:bg-slate-100 hover:text-slate-950'
								)}
								aria-current={isActiveRoute(item.href) ? 'page' : undefined}
							>
								<div class="text-sm font-medium">{item.label}</div>
								<div class={cn('text-xs', isActiveRoute(item.href) ? 'text-slate-300' : 'text-slate-500')}>
									{item.description}
								</div>
							</a>
						{/each}
					</nav>
				</CardContent>
			</Card>

			<div class="min-w-0">
				{@render children?.()}
			</div>
		</div>
	</div>
</div>
