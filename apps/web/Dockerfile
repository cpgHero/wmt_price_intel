FROM node:24.18.0-slim AS build

RUN npm install --global pnpm@11.20.0
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/typescript/contracts/package.json packages/typescript/contracts/package.json
RUN pnpm install --frozen-lockfile

COPY apps/web apps/web
COPY packages/typescript/contracts packages/typescript/contracts
COPY schemas schemas
RUN pnpm --filter @rci/web build

FROM node:24.18.0-slim AS runtime
WORKDIR /app
ENV HOSTNAME=0.0.0.0 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs --home-dir /app nextjs \
    && chown nextjs:nodejs /app
COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
USER nextjs

EXPOSE 3000
CMD ["node", "apps/web/server.js"]
