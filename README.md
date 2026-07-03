# Sales Performance Dashboard

Static executive dashboard rendered from a local DuckDB. Deployed to
GitHub Pages, single URL, no server.

**Live:** _paste the Pages URL here after enabling_

## What is in this repo

```
.
├── analytics.duckdb        cleaned data (source of truth for the build)
├── dashboard/
│   ├── build.py            renders docs/index.html from analytics.duckdb
│   └── README.md
├── docs/
│   └── index.html          the dashboard, served by GitHub Pages
├── requirements.txt
└── .gitignore
```

## Deploy to GitHub Pages

1. Push the repo to GitHub.
2. Settings → Pages → Source: branch `main`, folder `/docs`. Save.
3. GitHub returns a URL like `https://<user>.github.io/<repo>/`. Usually
   live within a minute.

## Rebuild locally (optional)

```
pip install -r requirements.txt
python dashboard/build.py
```

`build.py` reads `analytics.duckdb` and rewrites `docs/index.html`.
The database is checked into the repo so the dashboard is fully
reproducible without re-running ingestion.

## Layout of the dashboard

- **Row 1:** four KPI cards. Values are lifetime totals; delta chips
  compare the latest full year vs the year before.
- **Row 2:** full-width trend chart. Two views via the toggle top right:
  *Full historical* (default) and *Latest year overlay*.
- **Row 3:** profit margin by subcategory, sales share by category, and
  customer segment breakdown.
- **Row 4:** Year on Year summary with growth chips per metric.
