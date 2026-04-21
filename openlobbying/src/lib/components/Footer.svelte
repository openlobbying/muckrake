<script lang="ts">
	const footerLinks = [
		{ href: '/about', label: 'About' },
		{ href: '/licence', label: 'Licence' },
		{ href: '/privacy', label: 'Privacy Policy' }
	] as const;
</script>

<footer class="site-footer">
	<div class="footer-content">
		<div>
			<p class="footer-copy">
				OpenLobbying is a not-for-profit Community Interest Company registered in England and Wales (<a href="https://find-and-update.company-information.service.gov.uk/company/17146175" target="_blank" rel="noopener noreferrer">17146175</a>).
			</p>
		</div>
		<nav aria-label="Footer">
			<ul class="footer-links">
				{#each footerLinks as link (link.href)}
					<li>
						<a href={link.href}>{link.label}</a>
					</li>
				{/each}
			</ul>
		</nav>
	</div>
</footer>

<style>
	.site-footer {
		margin-top: 3rem;
		border-top: 1px solid #e5e7eb;
		background: #ffffff;
	}

	.footer-content {
		max-width: 1200px;
		margin: 0 auto;
		padding: 1.5rem;
		display: flex;
		flex-wrap: wrap;
		gap: 1rem 2rem;
		align-items: center;
		justify-content: space-between;
	}

	.footer-copy {
		margin: 0.4rem 0 0;
		font-size: 0.95rem;
		color: #64748b;
	}

	.footer-links {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
		padding: 0;
		margin: 0;
	}

	.footer-links a {
		color: #334155;
		text-decoration: none;
	}

	.footer-links a:hover {
		color: #1d4ed8;
	}
 </style>
