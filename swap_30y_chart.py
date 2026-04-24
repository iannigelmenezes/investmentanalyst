"""
Quick chart: EUR swap 30Y rate — last 10 years.
Series: YC/B.U2.EUR.4F.S_S_0.SV_C_YM.SR_30Y  (ECB SDW swap curve, par rates)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import datetime
import webbrowser
import plotly.graph_objects as go
from providers.ecb_sdw import _fetch_series

start = (datetime.date.today() - datetime.timedelta(days=365 * 10)).isoformat()
end   = datetime.date.today().isoformat()

print(f"Fetching EUR swap 30Y  {start} → {end} …")
df = _fetch_series("YC/B.U2.EUR.4F.S_S_0.SV_C_YM.SR_30Y",
                   start_period=start, end_period=end)

if df.empty:
    print("No data returned — series may not exist under this key.")
    sys.exit(1)

latest = df.iloc[-1]
print(f"Latest: {latest['date'].date()}  {latest['value']:.3f}%")
print(f"Rows  : {len(df)}")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df["date"], y=df["value"],
    mode="lines",
    name="EUR Swap 30Y",
    line=dict(color="#003399", width=2),
    hovertemplate="%{x|%d %b %Y}<br><b>%{y:.3f}%</b><extra></extra>",
))

fig.update_layout(
    title=dict(
        text=f"EUR Swap Rate — 30Y  |  10-year history  |  Latest: {latest['value']:.3f}% ({latest['date'].date()})",
        font=dict(size=15),
    ),
    xaxis=dict(
        title="",
        tickformat="%b %Y",
        showgrid=True, gridcolor="#e8eaf0",
        rangeslider=dict(visible=True, thickness=0.06),
    ),
    yaxis=dict(title="Rate (%)", showgrid=True, gridcolor="#e8eaf0"),
    plot_bgcolor="white", paper_bgcolor="white",
    hovermode="x unified",
    height=520,
    margin=dict(t=60, b=50, l=60, r=30),
)

out = os.path.join(os.path.dirname(__file__), "output.html")
fig.write_html(out)
print(f"\nChart saved → {out}")
webbrowser.open(f"file:///{out.replace(os.sep, '/')}")
print(f"\nSource : ECB SDW — YC/B.U2.EUR.4F.S_S_0.SV_C_YM.SR_30Y")
print(f"Vintage: {latest['date'].date()}")
