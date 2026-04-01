<script lang="ts">
	import { page } from '$app/state';
	import { isAdminUser } from '$lib/auth-roles';
	import Footer from '$lib/components/Footer.svelte';
	import favicon from '$lib/assets/favicon.svg';
	import type { LayoutProps } from './$types';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import * as NavigationMenu from '$lib/components/ui/navigation-menu';
	import { navigationMenuTriggerStyle } from '$lib/components/ui/navigation-menu/navigation-menu-trigger.svelte';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Github, Menu, Search } from '@lucide/svelte';
	import '../app.css';

	let { data, children }: LayoutProps = $props();
	let mobileMenuOpen = $state(false);
	let currentSearchQuery = $derived(page.url.searchParams.get('q') ?? '');
	let currentUser = $derived(data.user);
	let navItems = $derived([
		{ href: '/datasets', label: 'Datasets' },
		{ href: '/licence', label: 'Use our data' },
		{ href: '/about', label: 'About' }
	]);
	let adminUser = $derived(isAdminUser(currentUser));
	let accountLabel = $derived(currentUser ? currentUser.name : null);
	const githubUrl = 'https://github.com/openlobbying';
	const searchPlaceholder = 'Search organisations, politicians...';

	function closeMobileMenu(): void {
		mobileMenuOpen = false;
	}

	function isActiveRoute(href: string): boolean {
		const pathname = page.url.pathname;
		return pathname === href || pathname.startsWith(`${href}/`);
	}

	function getNavLinkClass(href: string): string {
		return navigationMenuTriggerStyle({
			class: isActiveRoute(href) ? 'bg-accent text-accent-foreground' : ''
		});
	}

	function getMobileNavLinkClass(href: string): string {
		return [
			'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
			isActiveRoute(href)
				? 'bg-accent text-accent-foreground'
				: 'text-foreground hover:bg-accent hover:text-accent-foreground'
		].join(' ');
	}

	function getAccountMenuClass(href: string): string {
		return [
			'block rounded-md px-3 py-2 text-sm transition-colors',
			isActiveRoute(href)
				? 'bg-accent text-accent-foreground'
				: 'text-foreground/80 hover:bg-accent hover:text-accent-foreground'
		].join(' ');
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<div class="app-shell">
	<nav class="main-nav">
		<div class="nav-content">
			<div class="flex items-center justify-between gap-4">
				<a href="/" class="logo">OpenLobbying</a>
				<div class="hidden items-center gap-2 md:flex">
					<form action="/search" method="GET" class="w-56 lg:w-72">
						<label class="relative block">
							<span class="sr-only">Search</span>
							<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center">
								<Search class="h-4 w-4 text-slate-400" />
							</span>
							<Input
								type="text"
								name="q"
								value={currentSearchQuery}
								placeholder={searchPlaceholder}
								class="h-9 bg-white pl-9"
							/>
						</label>
					</form>
					<NavigationMenu.Root viewport={false}>
						<NavigationMenu.List>
							{#each navItems as item (item.href)}
								<NavigationMenu.Item>
									<NavigationMenu.Link>
										{#snippet child()}
											<a
												href={item.href}
												class={getNavLinkClass(item.href)}
												aria-current={isActiveRoute(item.href) ? 'page' : undefined}
											>
												{item.label}
											</a>
										{/snippet}
									</NavigationMenu.Link>
								</NavigationMenu.Item>
							{/each}
							{#if currentUser}
								<NavigationMenu.Item>
									<NavigationMenu.Trigger>Account</NavigationMenu.Trigger>
									<NavigationMenu.Content class="min-w-52">
										<div class="space-y-1 p-1">
											<div class="px-3 py-2 text-sm text-slate-500">{accountLabel}</div>
											<a href="/account" class={getAccountMenuClass('/account')}>Account</a>
											{#if adminUser}
												<a href="/admin" class={getAccountMenuClass('/admin')}>Admin</a>
											{/if}
										</div>
									</NavigationMenu.Content>
								</NavigationMenu.Item>
							{/if}
							<NavigationMenu.Item>
								<NavigationMenu.Link>
									{#snippet child()}
										<a
											href={githubUrl}
											target="_blank"
											rel="noopener noreferrer"
											class={navigationMenuTriggerStyle({ class: 'inline-flex items-center' })}
											aria-label="OpenLobbying on GitHub"
										>
											<Github class="h-4 w-4" />
										</a>
									{/snippet}
								</NavigationMenu.Link>
							</NavigationMenu.Item>
						</NavigationMenu.List>
					</NavigationMenu.Root>
				</div>
				<div class="md:hidden">
					<Sheet.Root bind:open={mobileMenuOpen}>
						<Sheet.Trigger
							class="inline-flex h-9 w-9 items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
							aria-label="Open navigation"
						>
							<Menu class="h-5 w-5" />
						</Sheet.Trigger>
						<Sheet.Content side="right" class="w-[300px] sm:w-[340px]">
							<Sheet.Header>
								<Sheet.Title>Navigation</Sheet.Title>
							</Sheet.Header>
							<div class="flex flex-col gap-2 px-4 pb-4">
								<form
									action="/search"
									method="GET"
									onsubmit={() => {
										closeMobileMenu();
									}}
								>
									<label class="relative block">
										<span class="sr-only">Search</span>
										<span class="pointer-events-none absolute inset-y-0 left-3 flex items-center">
											<Search class="h-4 w-4 text-slate-400" />
										</span>
										<Input
											type="text"
											name="q"
											value={currentSearchQuery}
											placeholder={searchPlaceholder}
											class="h-10 bg-white pl-9"
										/>
									</label>
								</form>
								{#each navItems as item (item.href)}
									<a
										href={item.href}
										class={getMobileNavLinkClass(item.href)}
										aria-current={isActiveRoute(item.href) ? 'page' : undefined}
										onclick={() => {
											closeMobileMenu();
										}}
									>
										{item.label}
									</a>
							{/each}
							{#if currentUser}
								<div class="px-3 pt-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
									Account
								</div>
								<div class="px-3 text-sm text-slate-500">{accountLabel}</div>
								<a
									href="/account"
									class={getMobileNavLinkClass('/account')}
									onclick={() => {
										closeMobileMenu();
									}}
								>
									Account
								</a>
								{#if adminUser}
									<a
										href="/admin"
										class={getMobileNavLinkClass('/admin')}
										onclick={() => {
											closeMobileMenu();
										}}
									>
										Admin
									</a>
								{/if}
							{/if}
							<a
								href={githubUrl}
									target="_blank"
									rel="noopener noreferrer"
									class="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
									onclick={() => {
										closeMobileMenu();
									}}
								>
									<Github class="h-4 w-4" />
									<span>Open Source</span>
								</a>
							</div>
						</Sheet.Content>
					</Sheet.Root>
				</div>
			</div>
		</div>
	</nav>

	<div class="px-4 py-2">
		<Card class="gap-0 border-amber-400 bg-amber-100 py-0">
			<CardContent class="mx-auto max-w-[1200px] px-6 py-3 text-sm text-amber-900">
				This project is in alpha. The information is incomplete, presented for demonstration purposes only, and should not be relied on.
			</CardContent>
		</Card>
	</div>

	<main class="app-main">
		{@render children()}
	</main>

	<Footer />
</div>

<style>
	:global(body) {
		margin: 0;
		background-color: #f9fafb;
		color: #111827;
	}

	.app-shell {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	.main-nav {
		background: white;
		border-bottom: 1px solid #e5e7eb;
		padding: 1rem 0;
		position: sticky;
		top: 0;
		z-index: 40;
	}

	.nav-content {
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 1.5rem;
	}

	.logo {
		font-size: 1.25rem;
		font-weight: 700;
		color: #1e40af;
		text-decoration: none;
	}

	.app-main {
		flex: 1;
	}

</style>
