<script lang="ts">
	import { enhance } from '$app/forms';
	import AdminFlash from '$lib/components/admin/AdminFlash.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';

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
	<title>Admin Users - OpenLobbying</title>
	<meta name="description" content="Manage OpenLobbying users and account roles." />
</svelte:head>

<div class="space-y-6">
	<div class="space-y-2">
		<h2 class="text-2xl font-semibold tracking-tight text-slate-950">Users</h2>
		<p class="text-sm text-slate-600">Manage user roles and create accounts without leaving the admin area.</p>
	</div>

	<AdminFlash error={form?.error} success={form?.success} />

	<div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
		<Card class="border-slate-200">
			<CardHeader>
				<CardTitle>All users</CardTitle>
				<CardDescription>{data.total} user{data.total === 1 ? '' : 's'}.</CardDescription>
			</CardHeader>
			<CardContent>
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead>Name</TableHead>
							<TableHead>Email</TableHead>
							<TableHead>Role</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Created</TableHead>
							<TableHead class="w-[180px]">Action</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#each data.users as user (user.id)}
							<TableRow>
								<TableCell class="align-top whitespace-normal">
									<div class="font-medium text-slate-900">{user.name}</div>
									<div class="mt-1 font-mono text-xs text-slate-500">{user.id}</div>
								</TableCell>
								<TableCell class="align-top whitespace-normal text-slate-600">{user.email}</TableCell>
								<TableCell class="align-top text-slate-600">{user.role ?? 'user'}</TableCell>
								<TableCell class="align-top text-slate-600">
									{user.banned ? 'Banned' : 'Active'}
								</TableCell>
								<TableCell class="align-top whitespace-normal text-slate-600">
									{new Date(user.createdAt).toLocaleString('en-GB')}
								</TableCell>
								<TableCell class="align-top">
									<form method="POST" action="?/setRole" use:enhance class="flex items-center gap-2">
										<input type="hidden" name="userId" value={user.id} />
										<select
											name="role"
											value={user.role ?? 'user'}
											class="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-slate-300"
										>
											<option value="user">user</option>
											<option value="admin">admin</option>
										</select>
										<Button type="submit" size="sm">Save</Button>
									</form>
								</TableCell>
							</TableRow>
						{/each}
					</TableBody>
				</Table>
			</CardContent>
		</Card>

		<Card class="border-slate-200">
			<CardHeader>
				<CardTitle>Create user</CardTitle>
				<CardDescription>Manual account creation for admin use.</CardDescription>
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
							class="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-slate-300"
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
