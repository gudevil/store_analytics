# Background

This dashboard is the deliverable for Q6, where source data used was from the initial setup before answering Q1-Q5.

The ideation behind this dashboard is creating a dashboard based on the persona for the Head of Sales & Head of Commercial where I aim for them to answer 3 main questions from first glance of the dashboard:
1. Are we growing?
2. Where is margin leaking?
3. Which of the customer base is of high value in terms of margin and sales volume?

In the dashboard, I included the lifetime value as key KPI index to see how is the business doing, and delta for the latest year available data (2017 vs 2016) to see in terms of yearly growth. If this was live data then itd be current year vs last year.


## Run

```
pip install -r requirements.txt
python dashboard/build.py
```

Reads `../analytics.duckdb` and writes `../docs/index.html`.
  
