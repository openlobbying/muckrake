## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

Frontend calls use relative `/api/*` routes. In local development, Vite proxies `/api` to `http://127.0.0.1:8000`.

## Authentication

This app uses Better Auth for email/password login.

- Auth tables are created automatically in the database pointed to by `MUCKRAKE_DATABASE_URL`.
- Set `AUTH_SECRET` in production. In development only, the app falls back to a fixed local secret.
- Better Auth runs on `/auth/*` so it does not clash with the existing `/api/*` FastAPI proxy in development.
- Better Auth's admin plugin is enabled, and the admin panel lives at `/admin`.
- Admin access is role-based using Better Auth's built-in `user` and `admin` roles.
- Admins can be promoted or demoted from `/admin`.
- The login page is at `/login`.
- The protected example page is at `/account`.

## Building

To create a production version of your app:

```sh
npm run build
```

You can preview the production build with `npm run preview`.

## Deployment notes

- This app uses `@sveltejs/adapter-node`.
- Production runtime command is `node build`.
- In production we expect a reverse proxy (Caddy/Nginx) in front of the Node process.

See `../ops/README.md` for the deployment runbook and `../ops/` for service templates and proxy config used by this project.
