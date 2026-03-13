## Developing

Once you've created a project and installed dependencies with `npm install` (or `pnpm install` or `yarn`), start a development server:

```sh
npm run dev

# or start the server and open the app in a new browser tab
npm run dev -- --open
```

Frontend calls use relative `/api/*` routes. In local development, Vite proxies `/api` to `http://127.0.0.1:8000`.

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

See `../docs/deploy/` for service templates and proxy config used by this project.
