# SKYNET Payments Dashboard

An interactive Streamlit dashboard for analysing SKYNET-AP WiFi mobile-money
transaction exports from Hubtel. Upload a CSV and explore revenue, fees, plans,
locations, networks, peak hours, top customers and refunds — all with interactive
Plotly charts.

## Run it

```powershell
# from this folder
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens at http://localhost:8501. If you don't upload a file, it loads the
bundled `h-data.csv` as a sample so the dashboard is never empty.

## Notes on the data

- `Description` encodes the plan + location, e.g. `SKYNET-AP WiFi - Daily - THEPOINT`.
- Older rows have no location (e.g. `SKYNET-AP WiFi - Daily`); at that time only one
  location existed, so those are attributed to **DREAMERS**.
- Refunded transactions (`Is Refunded = True`) are flagged and excluded from net revenue.
