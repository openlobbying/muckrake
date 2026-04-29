<script lang="ts">
	import { ChevronDown, ExternalLink, Users, PencilLine } from "@lucide/svelte";
	import { getEntityRoute } from "$lib/util/routes";
	import { getTypeInfo } from "./registry";
	import { formatQuarterRange, formatFullDate, formatDateRange } from "$lib/util/dates";
	import TimelineDetails from './TimelineDetails.svelte';
	import { getPropertyLabel, getTimelinePrimaryRows } from '$lib/presentation/property-profile';
import { formatLabel, isEntity, renderableValue, type DetailRow } from '$lib/util/detail';

	interface Props {
		activity: any;
		currentEntityId?: string;
	}

	let { activity, currentEntityId = "" }: Props = $props();

	const info = $derived(getTypeInfo(activity.type));
	const isWritten = $derived(
		activity.type === "Evidence" &&
			activity.properties.keywords?.some((k: string) =>
				k.includes("Written Evidence"),
			),
	);
	const Icon = $derived(isWritten ? PencilLine : info.icon);

	const formattedDate = $derived.by(() => {
		const props = activity.properties || {};
		if (props.startDate?.[0] || props.endDate?.[0]) {
			return activity.type === "Representation"
				? formatQuarterRange(props.startDate?.[0], props.endDate?.[0])
				: formatDateRange(props.startDate?.[0], props.endDate?.[0]);
		}
		return activity.type === "Representation"
			? formatQuarterRange(
					props.startDate?.[0] || activity.date,
					props.endDate?.[0],
				)
			: activity.date
				? formatFullDate(activity.date)
				: "Unknown Date";
	});

	const isPaymentLike = $derived(
		activity.type === 'Payment' || activity.type === 'Donation' || activity.type === 'Gift' || activity.type === 'Hospitality'
	);
	const isVisitLike = $derived(activity.type === 'Visit' || activity.type === 'Trip');
	const isOwnershipLike = $derived(activity.type === 'Ownership' || activity.type === 'Property');

	const linkId = $derived(activity.id?.replace(/-(start|end)$/, ""));
	const fullRecordHref = $derived(getEntityRoute(linkId, activity.type));
	const primaryRows = $derived<DetailRow[]>(getTimelinePrimaryRows(activity.type, activity.properties));
	let detailsOpen = $state(false);

	function getPrimaryRowValues(row: DetailRow): any[] {
		if (row.key !== 'involved') {
			return row.values;
		}
		return row.values.filter((value) => !(isEntity(value) && value.id === currentEntityId));
	}

	function formatCurrency(amount: number, currency: string = "GBP") {
		return new Intl.NumberFormat("en-GB", {
			style: "currency",
			currency: currency || "GBP",
			maximumFractionDigits: 0,
		}).format(amount);
	}
</script>

{#snippet renderEntityList(entities: any[])}
	{#each entities as entity, i}
		{#if i > 0}
			{#if i === entities.length - 1}{" and "}{:else},
			{/if}
		{/if}
		<a
			href={getEntityRoute(entity.id, entity.schema)}
			class="text-blue-600 hover:underline font-medium"
			>{entity.caption}</a
		>
	{/each}
{/snippet}

{#snippet richDescription()}
	{#if activity.type === "Representation" && activity.properties}
		{@const agents = activity.properties.agent || []}
		{@const clients = activity.properties.client || []}
		{@const role = activity.properties.role?.[0]}
		{#if clients.some((c: any) => c.id === currentEntityId) && agents.length > 0}
			Retained
			{@render renderEntityList(agents)}
			{#if role}
				as a {role}{/if}
		{:else if agents.some((a: any) => a.id === currentEntityId) && clients.length > 0}
			Retained by
			{@render renderEntityList(clients)}
			{#if role}
				as a {role}{/if}
		{:else}
			{activity.title}
		{/if}
	{:else if isPaymentLike && activity.properties}
		{@const payers = activity.properties.payer || []}
		{@const beneficiaries = activity.properties.beneficiary || []}
		{@const purpose = activity.properties.purpose?.[0]}
		{@const programme =
			activity.properties.programme?.[0] ||
			(purpose === "Loan" || purpose === "Donation" ? purpose : undefined)}
		{@const amount = activity.properties.amount?.[0]}
		{@const currency = activity.properties.currency?.[0]}

		{#if payers.some((p: any) => p.id === currentEntityId) && beneficiaries.length > 0}
			{#if activity.type === "Gift"}
				{purpose || 'Gave gift'}
			{:else if activity.type === "Donation"}
				Donated
			{:else if programme === "Loan"}
				Loaned
			{:else if programme === "Donation"}
				Donated
			{:else if activity.type === "Hospitality"}
				Provided hospitality
			{:else}
				Paid
			{/if}
			{#if amount}
				<strong>{formatCurrency(amount, currency)}</strong>
			{/if}
			{#if amount && activity.type === "Gift" && purpose}
				to
			{:else if activity.type !== "Gift"}
				to
			{/if}
			{@render renderEntityList(beneficiaries)}
			{#if purpose && purpose !== "Loan" && purpose !== "Donation" && activity.type !== "Gift"}
				for {purpose}{/if}
		{:else if beneficiaries.some((b: any) => b.id === currentEntityId) && payers.length > 0}
			Received
			{#if activity.type === "Gift"}
				{purpose || 'gift'}
			{:else if activity.type === "Hospitality"}
				hospitality from
			{:else if activity.type === "Donation"}
				donation of
			{:else if programme === "Loan"}
				loan of
			{:else if programme === "Donation"}
				donation of
			{/if}
			{#if amount}
				<strong>{formatCurrency(amount, currency)}</strong>
			{/if}
			{#if activity.type !== "Hospitality"}
				from
			{/if}
			{@render renderEntityList(payers)}
			{#if purpose && purpose !== "Loan" && purpose !== "Donation" && activity.type !== "Gift"}
				for {purpose}{/if}
		{:else}
			{activity.title}
		{/if}
	{:else if activity.type === "Employment" && activity.properties}
		{@const employees = activity.properties.employee || []}
		{@const employers = activity.properties.employer || []}
		{@const role = activity.properties.role?.[0]}
		{#if employees.some((e: any) => e.id === currentEntityId) && employers.length > 0}
			{#if role}
				{role} at
			{:else}
				Employed by
			{/if}
			{@render renderEntityList(employers)}
		{:else if employers.some((e: any) => e.id === currentEntityId) && employees.length > 0}
			Employed
			{@render renderEntityList(employees)}
			{#if role}
				as {role}{/if}
		{:else}
			{activity.title}
		{/if}
	{:else if activity.type === "Directorship" && activity.properties}
		{@const directors = activity.properties.director || []}
		{@const organizations = activity.properties.organization || []}
		{#if directors.some((d: any) => d.id === currentEntityId) && organizations.length > 0}
			Director of
			{@render renderEntityList(organizations)}
		{:else if organizations.some((o: any) => o.id === currentEntityId) && directors.length > 0}
			{@render renderEntityList(directors)}
			appointed as director
		{:else}
			{activity.title}
		{/if}
	{:else if isOwnershipLike && activity.properties}
		{@const owners = activity.properties.owner || []}
		{@const assets = activity.properties.asset || []}
		{#if owners.some((o: any) => o.id === currentEntityId) && assets.length > 0}
			{#if activity.type === "Property"}
				Owns property:
			{:else}
				Shareholding in
			{/if}
			{@render renderEntityList(assets)}
		{:else if assets.some((a: any) => a.id === currentEntityId) && owners.length > 0}
			Owned by
			{@render renderEntityList(owners)}
		{:else}
			{activity.title}
		{/if}
	{:else if activity.type === "Family" && activity.properties}
		{@const persons = activity.properties.person || []}
		{@const relatives = activity.properties.relative || []}
		{@const relationship = activity.properties.relationship?.[0]}
		{#if persons.some((p: any) => p.id === currentEntityId) && relatives.length > 0}
			{#if relationship}
				{relationship}:
			{:else}
				Family member:
			{/if}
			{@render renderEntityList(relatives)}
		{:else if relatives.some((r: any) => r.id === currentEntityId) && persons.length > 0}
			{#if relationship}
				{relationship} of
			{:else}
				Related to
			{/if}
			{@render renderEntityList(persons)}
		{:else}
			{activity.title}
		{/if}
	{:else if isVisitLike && activity.properties}
		{@const countries = activity.properties.country || []}
		{@const locations = activity.properties.location || []}
		{@const involved = activity.properties.involved || []}
		{#if involved.some((p: any) => p.id === currentEntityId)}
			Visit to
		{:else if involved.length > 0}
			{@render renderEntityList(involved)}
			{involved.length === 1 ? "visited" : "visited"}
		{:else}
			Visit to
		{/if}
		{#if locations.length > 0}
			{locations.join(", ")}
		{:else if countries.length > 0}
			{countries.join(", ")}
		{:else}
			international destination
		{/if}
	{:else if activity.type === "Evidence" && activity.properties}
		{@const organizers = activity.properties.organizer || []}
		{#if organizers.some((o: any) => o.id === currentEntityId)}
			Received {isWritten ? "written" : "oral"} evidence
		{:else}
			{isWritten ? "Submitted written" : "Provided oral"} evidence to the
			{#if organizers.length > 0}
				{@render renderEntityList(organizers)}
			{:else}
				committee
			{/if}
		{/if}
	{:else if activity.type === "Meeting" && activity.properties}
		{@const organizers = activity.properties.organizer || []}
		{@const involved = activity.properties.involved || []}
		{#if organizers.some((o: any) => o.id === currentEntityId)}
			Met with
			{@render renderEntityList(involved)}
		{:else if involved.some((i: any) => i.id === currentEntityId)}
			Meeting with
			{@render renderEntityList(organizers)}
		{:else}
			{activity.title}
		{/if}
	{:else if activity.type === "UnknownLink" && activity.properties}
		{@const summary = activity.properties.summary?.[0]}
		{@const description = activity.properties.description?.[0]}
		{summary || description || activity.title}
	{:else}
		{activity.title}
	{/if}
{/snippet}

<div class="relative flex items-start space-x-4">
	<!-- Marker -->
	<div
		class="relative z-10 flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center shadow-sm border-2"
		style="background-color: {info.badgeBg}; border-color: {info.markerColor}; color: {info.markerColor};"
	>
		<Icon class="w-5 h-5" />
	</div>

	<!-- Content -->
	<div class="flex-1 min-w-0 pb-8">
		<div
			class="bg-white rounded-lg p-4 border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
		>
			<div class="flex items-start justify-between mb-1">
				<div class="flex-1">
					<h3 class="text-sm font-semibold text-gray-900">
						{@render richDescription()}
					</h3>
					<p class="text-xs text-gray-500 mt-1">{formattedDate}</p>
				</div>
				<span
					class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border capitalize"
					style="background-color: {info.badgeBg}; color: {info.markerColor}; border-color: {info.markerColor}40;"
				>
					{info.label || activity.type}
				</span>
			</div>

		{#if isVisitLike && activity.properties}
			{@const purpose = activity.properties.summary?.[0]}
		{#if purpose}
				<p class="text-sm text-gray-700 mt-2">
					<span class="text-gray-500">Purpose:</span>
					{purpose}
				</p>
			{/if}
		{/if}

			{#if primaryRows.length > 0}
				<div class="space-y-1.5 mt-2">
					{#each primaryRows as row (row.key)}
						{@const rowValues = getPrimaryRowValues(row)}
						{#if rowValues.length > 0}
							<p class="text-sm text-gray-700 whitespace-pre-line flex items-start gap-2">
								{#if row.key === 'involved'}
									<Users class="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-gray-500" />
								{/if}
								<span>
								<span class="text-gray-500">{formatLabel(getPropertyLabel(activity.type, row.key))}:</span>
								{#each rowValues as value, i}
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
								</span>
							</p>
						{/if}
					{/each}
				</div>
			{/if}

			{#if isOwnershipLike && activity.properties}
				{@const desc = activity.properties.description?.[0]}
				{#if desc}
					<p class="text-sm text-gray-700 mt-2">
						{desc}
					</p>
				{/if}
			{/if}

			{#if activity.description && activity.type !== "Representation" && !isPaymentLike && !isVisitLike && !isOwnershipLike}
				<p class="text-sm text-gray-700 mt-2">{activity.description}</p>
			{/if}

			{#if activity.amount && activity.type !== "Payment" && activity.type !== "Donation" && activity.type !== "Gift"}
				<div class="mt-2 text-sm font-semibold text-gray-900">
					{formatCurrency(activity.amount)}
				</div>
			{/if}

			{#if detailsOpen}
				<TimelineDetails {activity} />
			{/if}

			<div class="mt-4 flex flex-wrap items-center gap-3 border-t border-gray-100 pt-3 text-xs text-gray-500">
				<button
					type="button"
					onclick={() => (detailsOpen = !detailsOpen)}
					aria-expanded={detailsOpen}
					class="inline-flex items-center gap-1 hover:text-gray-900"
				>
					{detailsOpen ? 'Hide details' : 'Details'}
					<ChevronDown class="h-3.5 w-3.5 {detailsOpen ? 'rotate-180' : ''} transition-transform" />
				</button>
				<a href={fullRecordHref} class="inline-flex items-center gap-1 hover:text-blue-600 hover:underline">
					Open full record
					<ExternalLink class="h-3.5 w-3.5" />
				</a>
			</div>
		</div>
	</div>
</div>
