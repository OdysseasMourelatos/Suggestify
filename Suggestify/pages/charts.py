# charts.py

import plotly.graph_objects as go
import pandas as pd
from config import *

_LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color=TEXT_DIM, size=12),
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)", zeroline=False, fixedrange=True),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)", zeroline=False, fixedrange=True),
    margin=dict(t=30, b=40, l=50, r=20),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="#1C1C1C", bordercolor="rgba(255,255,255,0.1)", font=dict(color=TEXT, size=13)),
    dragmode=False,
)

def themed(fig: go.Figure, **extra) -> go.Figure:
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_layout(**extra)
    return fig

def chart_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["stream_count"], name="Streams", mode="lines+markers",
        line=dict(color=GREEN, width=3, shape='spline'),
        marker=dict(size=7, color=GREEN, line=dict(width=2, color=BG)), fill="tozeroy", fillcolor=GREEN_XLO
    ))
    fig.add_trace(go.Bar(x=df["period"], y=df["hours_played"], name="Hours", marker_color="rgba(29,185,84,0.2)", yaxis="y2"))
    return themed(fig, yaxis=dict(title=dict(text="Streams", font=dict(color=TEXT_MID))),
        yaxis2=dict(title=dict(text="Hours", font=dict(color=TEXT_MID)), overlaying="y", side="right", showgrid=False, fixedrange=True),
        hovermode="x unified", legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center")
    )

def chart_multi_trend(df: pd.DataFrame) -> go.Figure:
    df = df.copy()
    df["period"] = pd.to_datetime(df["period"])
    fig = go.Figure()
    colors = [GREEN, "#4FC3F7", "#F48FB1", "#FFD54F", "#B39DDB"]
    for idx, track in enumerate(df["track_title"].unique()):
        track_df = df[df["track_title"] == track]
        fig.add_trace(go.Scatter(x=track_df["period"], y=track_df["stream_count"], name=track, mode="lines",
            line=dict(width=2.5, shape='spline', color=colors[idx % len(colors)]),
        ))
    return themed(fig, yaxis=dict(title=dict(text="Streams", font=dict(color=TEXT_MID))), hovermode="x unified", legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"))
    
def chart_heatmap(df: pd.DataFrame) -> go.Figure:
    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = df.pivot(index="dow", columns="hour", values="stream_count").reindex(index=range(1, 8), columns=range(24)).fillna(0)
    fig = go.Figure(go.Heatmap(z=pivot.values, x=[f"{h:02d}" for h in range(24)], y=DOW,
        colorscale=[[0, BG], [0.15, "rgba(29,185,84,0.1)"], [0.4, GREEN_DIM], [1, GREEN]],
        hoverongaps=False, xgap=3, ygap=3, hovertemplate="<b>%{y}</b> at <b>%{x}:00</b><br>%{z} streams<extra></extra>"
    ))
    return themed(fig, xaxis_title="Hour", yaxis_title="", margin=dict(t=20, b=50, l=60, r=20),
                  height=300, yaxis=dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)", zeroline=False, fixedrange=True, autorange="reversed"))

def chart_bar(x, y, xlabel: str) -> go.Figure:
    max_val = max(y) if y else 0
    colors = [GREEN if v == max_val else "rgba(29,185,84,0.35)" for v in y]
    fig = go.Figure(go.Bar(x=x, y=y, marker_color=colors, marker_line=dict(width=0), hovertemplate="<b>%{x}</b><br>%{y:,} streams<extra></extra>"))
    return themed(fig, xaxis_title=xlabel, yaxis_title="Streams", bargap=0.25)

def chart_year_bar(df: pd.DataFrame) -> go.Figure:
    years = df["year"].astype(str).tolist()
    streams = df["stream_count"].tolist()
    hours = df["hours_played"].tolist()
    max_val = max(streams) if streams else 0
    colors = [GREEN if v == max_val else "rgba(29,185,84,0.35)" for v in streams]
    fig = go.Figure(go.Bar(
        x=years, y=streams, marker_color=colors, marker_line=dict(width=0), customdata=hours,
        text=[f"{h:,.0f}h" for h in hours], textposition="outside", textfont=dict(color=TEXT_MID, size=11),
        cliponaxis=False, hovertemplate="<b>%{x}</b><br>%{y:,} streams<br>%{customdata:,.1f}h listened<extra></extra>"
    ))
    return themed(fig, xaxis_title="", yaxis_title="Streams", bargap=0.4, margin=dict(t=40, b=40, l=50, r=20))

def chart_donut(labels, values, colors) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.66, marker=dict(colors=colors, line=dict(color=BG, width=4)),
        sort=False, textinfo="percent", textfont=dict(color=TEXT, size=13, family="Inter, sans-serif"),
        hovertemplate="<b>%{label}</b><br>%{value:,} streams (%{percent})<extra></extra>"
    ))
    fig.update_layout(showlegend=False)
    return themed(fig, margin=dict(t=10, b=10, l=10, r=10))