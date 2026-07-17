# =============================================================================
# Enterprise RAG AI Assistant — Frontend Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (deps):    Install all Node.js dependencies.
#   Stage 2 (builder): Build the Next.js production bundle.
#   Stage 3 (runtime): Copy only the standalone output (minimal image).
#
# The Next.js standalone output mode drastically reduces the final image size
# by including only the files required to run the app (no node_modules).
# =============================================================================

# ── Stage 1: Dependency Installation ─────────────────────────────────────────
FROM node:20-alpine AS deps

# Install libc6-compat for compatibility with some native binaries on Alpine.
RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy package files first for optimal layer caching.
COPY package.json package-lock.json* ./

RUN npm ci --legacy-peer-deps


# ── Stage 2: Application Build ────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy installed node_modules from the deps stage.
COPY --from=deps /app/node_modules ./node_modules

# Copy the rest of the application source.
COPY . .

# Build environment variables (non-secret, baked into the bundle).
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

# Build the Next.js production bundle.
RUN npm run build


# ── Stage 3: Runtime ──────────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Create a non-root user for security.
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

WORKDIR /app

# Copy the standalone output from the builder.
# Next.js standalone mode bundles only what is needed to run.
# Note: Requires `output: "standalone"` in next.config.ts (see next.config.ts).
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static    ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public           ./public

USER nextjs

EXPOSE 3000

ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

# Docker health check.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

CMD ["node", "server.js"]
