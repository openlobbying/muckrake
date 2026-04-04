<script lang="ts">
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';

	interface AdminUser {
		id: string;
		email: string;
		name: string;
		role?: string | null;
		banned?: boolean | null;
		createdAt: string | Date;
	}

	interface AdminPageData {
		users: AdminUser[];
		total: number;
	}

	interface AdminActionData {
		error?: string;
		success?: string;
	}

	let { data, form }: { data: AdminPageData; form: AdminActionData | null } = $props();
</script>

<svelte:head>
	<title>Admin - OpenLobbying</title>
	<meta
		name="description"
		content="Basic Better Auth admin panel for managing OpenLobbying users."
	/>
</svelte:head>

<div class="bg-gradient-to-b from-slate-50 via-white to-amber-50 px-4 py-14 sm:px-6">
	<div class="mx-auto max-w-6xl space-y-6">
		<div class="space-y-3">
			<p class="text-sm font-semibold uppercase tracking-[0.24em] text-amber-700">Admin</p>
			<h1 class="text-4xl font-semibold tracking-tight text-slate-900">User management</h1>
			<p class="max-w-3xl text-base leading-7 text-slate-600">
				Edit user roles and manage account statuses.
			</p>
		</div>

		{#if form?.error}
			<p class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
				{form.error}
			</p>
		{/if}

		{#if form?.success}
			<p class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
				{form.success}
			</p>
		{/if}

		<div class="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
			<Card class="rounded-3xl border-amber-200 bg-amber-50/70 lg:col-span-2">
				<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
					<div class="space-y-2">
						<CardTitle>Dedupe review</CardTitle>
						<CardDescription>
							Compare the existing pair queue with a new checkbox-based cluster review MVP.
						</CardDescription>
					</div>
					<div class="flex flex-wrap gap-3">
						<a
							href={resolve('/admin/dedupe')}
							class="inline-flex h-10 items-center justify-center rounded-full bg-slate-900 px-4 text-sm font-medium text-white transition-colors hover:bg-slate-800"
						>
							Open pair queue
						</a>
						<a
							href={resolve('/admin/dedupe-clusters')}
							class="inline-flex h-10 items-center justify-center rounded-full border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900"
						>
							Open cluster queue
						</a>
					</div>
				</CardHeader>
			</Card>

			<Card class="rounded-3xl">
				<CardHeader>
					<CardTitle>Users</CardTitle>
					<CardDescription>{data.total} user{data.total === 1 ? '' : 's'} returned.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="overflow-x-auto">
						<table class="w-full min-w-[720px] text-left text-sm">
							<thead class="border-b border-slate-200 text-slate-500">
								<tr>
									<th class="px-3 py-2 font-medium">Name</th>
									<th class="px-3 py-2 font-medium">Email</th>
									<th class="px-3 py-2 font-medium">Role</th>
									<th class="px-3 py-2 font-medium">Status</th>
									<th class="px-3 py-2 font-medium">Created</th>
									<th class="px-3 py-2 font-medium">Action</th>
								</tr>
							</thead>
							<tbody>
								{#each data.users as user (user.id)}
									<tr class="border-b border-slate-100 align-top">
										<td class="px-3 py-3 font-medium text-slate-900">
											<div>{user.name}</div>
											<div class="mt-1 font-mono text-xs text-slate-500">{user.id}</div>
										</td>
										<td class="px-3 py-3 text-slate-600">{user.email}</td>
										<td class="px-3 py-3 text-slate-600">{user.role ?? 'user'}</td>
										<td class="px-3 py-3 text-slate-600">
											{user.banned ? 'Banned' : 'Active'}
										</td>
										<td class="px-3 py-3 text-slate-600">
											{new Date(user.createdAt).toLocaleString('en-GB')}
										</td>
									<td class="px-3 py-3">
										<form method="POST" action="?/setRole" use:enhance class="flex items-center gap-2">
											<input type="hidden" name="userId" value={user.id} />
											<select
												name="role"
												value={user.role ?? 'user'}
												class="border-input bg-background ring-offset-background focus-visible:ring-ring/50 h-9 w-28 rounded-md border px-3 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
											>
												<option value="user">user</option>
												<option value="admin">admin</option>
											</select>
											<Button type="submit" size="sm">Save</Button>
										</form>
									</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</CardContent>
			</Card>

			<Card class="rounded-3xl">
				<CardHeader>
					<CardTitle>Create user</CardTitle>
					<CardDescription>
						Manual creation path in case you want to seed an account without the public signup form.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<form method="POST" action="?/createUser" use:enhance class="space-y-4">
						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Name</span>
							<Input name="name" placeholder="Nicu" />
						</label>

						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Email</span>
							<Input name="email" type="email" placeholder="nicu@example.org" />
						</label>

						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Password</span>
							<Input name="password" type="password" placeholder="Strong password" />
						</label>

						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Role</span>
							<select
								name="role"
								class="border-input bg-background ring-offset-background focus-visible:ring-ring/50 h-10 w-full rounded-md border px-3 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px]"
							>
								<option value="user">user</option>
								<option value="admin">admin</option>
							</select>
						</label>

						<Button type="submit" class="w-full">Create user</Button>
					</form>
				</CardContent>
			</Card>
		</div>
	</div>
</div>
