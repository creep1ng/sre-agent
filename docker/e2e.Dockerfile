# Digest verified against Microsoft Container Registry on 2026-09-08. The
# Playwright version matches package-lock.json (1.63.0).
FROM mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

WORKDIR /e2e
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# The runner contains only its test inputs. It never bind-mounts application
# source or starts an API process; it consumes the candidate's Compose images.
COPY playwright.production.config.js ./
COPY tests/browser ./tests/browser
RUN chown -R pwuser:pwuser /e2e

USER pwuser
CMD ["npx", "playwright", "test", "--config=playwright.production.config.js"]
