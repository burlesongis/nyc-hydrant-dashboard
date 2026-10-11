# app.py
# ---------------------------------------------------------------------------
# Streamlit dashboard for NYC hydrant density analysis.
#
# Displays an interactive map and data table of fire hydrant density
# by neighborhood, with sidebar filters for borough and density range.
#
# Data:     data.parquet (GeoParquet from Lesson 2.5)
#           262 NYC neighborhoods with hydrant_count, area_km2,
#           and hydrants_per_km2 columns.
#
# Usage:    streamlit run app.py
# ---------------------------------------------------------------------------

import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import matplotlib.colors as mcolors
import numpy as np
import matplotlib.pyplot as plt

# --- Page config ----------------------------------------------------------
st.set_page_config(
    page_title="NYC Hydrant Density",
    page_icon="🚒",
    layout="wide",
)

# --- Load data (cached so it only reads once) -----------------------------
@st.cache_data
def load_data():
    gdf = gpd.read_parquet("data.parquet")
    # Only keep residential neighborhoods (ntatype '0') that have hydrants
    gdf = gdf[gdf["ntatype"] == "0"].copy()
    # Round for cleaner display
    gdf["area_km2"] = gdf["area_km2"].round(2)
    gdf["hydrants_per_km2"] = gdf["hydrants_per_km2"].round(1)
    return gdf

data = load_data()

# --- Sidebar filters ------------------------------------------------------
st.sidebar.header("Filters")

# Borough filter
boroughs = sorted(data["boroname"].unique())
selected_boroughs = st.sidebar.multiselect(
    "Borough",
    options=boroughs,
    default=boroughs,
)

# Density range slider
# Round the slider ends to multiples of the step (5) so the full data range
# is always selectable; otherwise the top handle snaps below the max value
# and silently drops the densest neighborhood.
density_min = float(np.floor(data["hydrants_per_km2"].min() / 5) * 5)
density_max = float(np.ceil(data["hydrants_per_km2"].max() / 5) * 5)
density_range = st.sidebar.slider(
    "Hydrant density (per km²)",
    min_value=density_min,
    max_value=density_max,
    value=(density_min, density_max),
    step=5.0,
)

# Apply filters
filtered = data[
    (data["boroname"].isin(selected_boroughs))
    & (data["hydrants_per_km2"] >= density_range[0])
    & (data["hydrants_per_km2"] <= density_range[1])
].copy()

# --- Title and description ------------------------------------------------
st.title("NYC Fire Hydrant Density")
st.markdown(
    "Explore fire hydrant density across NYC neighborhoods. "
    "Use the sidebar to filter by borough and density range."
)

# --- Metrics row ----------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Neighborhoods", f"{len(filtered):,}")
col2.metric("Total Hydrants", f"{int(filtered['hydrant_count'].sum()):,}")
col3.metric(
    "Mean Density",
    f"{filtered['hydrants_per_km2'].mean():.1f} / km²" if len(filtered) > 0 else "—",
)
col4.metric(
    "Max Density",
    f"{filtered['hydrants_per_km2'].max():.1f} / km²" if len(filtered) > 0 else "—",
)

# --- Map ------------------------------------------------------------------
st.subheader("Map")

if len(filtered) == 0:
    st.warning("No neighborhoods match the current filters. Adjust the sidebar.")
else:
    # Build a color map matching the YlOrRd scheme used in Lessons 2.5 and 3.3
    colormap = mcolors.LinearSegmentedColormap.from_list(
        "hydrant",
        ["#ffffcc", "#fed976", "#fd8d3c", "#e31a1c", "#800026"],
    )
    norm = mcolors.Normalize(
        vmin=data["hydrants_per_km2"].min(),
        vmax=data["hydrants_per_km2"].max(),
    )

    def get_color(density):
        rgba = colormap(norm(density))
        return mcolors.to_hex(rgba)

    # Create the Folium map centered on the filtered data
    bounds = filtered.total_bounds  # [minx, miny, maxx, maxy]
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",  # CARTO tiles now require an API key
    )

    # Add each neighborhood as a colored polygon with a tooltip
    for _, row in filtered.iterrows():
        color = get_color(row["hydrants_per_km2"])

        # Convert geometry to GeoJSON for Folium
        geo_json = gpd.GeoSeries([row["geometry"]]).__geo_interface__

        folium.GeoJson(
            geo_json,
            style_function=lambda feature, c=color: {
                "fillColor": c,
                "color": "#333",
                "weight": 0.5,
                "fillOpacity": 0.7,
            },
            tooltip=folium.Tooltip(
                f"<b>{row['ntaname']}</b><br>"
                f"{row['boroname']}<br>"
                f"Hydrants: {row['hydrant_count']}<br>"
                f"Density: {row['hydrants_per_km2']} / km²"
            ),
        ).add_to(m)

    # Fit the map to the filtered extent
    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    st_folium(m, use_container_width=True, height=500)

# --- Top 15 bar chart -----------------------------------------------------
st.subheader("Top 15 Neighborhoods by Density")

if len(filtered) > 0:
    borough_colors = {
        "Manhattan": "#e31a1c",
        "Brooklyn": "#1f78b4",
        "Bronx": "#33a02c",
        "Queens": "#ff7f00",
        "Staten Island": "#6a3d9a",
    }
    top15 = (
        filtered.sort_values("hydrants_per_km2", ascending=False)
        .head(15)
        .iloc[::-1]  # reverse so the densest bar is at the top
    )
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(
        top15["ntaname"],
        top15["hydrants_per_km2"],
        color=[borough_colors.get(b, "#999999") for b in top15["boroname"]],
    )
    ax.set_xlabel("Hydrants per km\u00b2")
    ax.spines[["top", "right"]].set_visible(False)

    # Legend only for boroughs that appear in the chart
    present = [b for b in borough_colors if b in set(top15["boroname"])]
    ax.legend(
        handles=[plt.Rectangle((0, 0), 1, 1, color=borough_colors[b]) for b in present],
        labels=present,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),  # below the x-axis label, out of the bars
        ncol=len(present),            # one row
        frameon=False,
    )
    fig.tight_layout()

    chart_col, _ = st.columns([4, 1])
    with chart_col:
        st.pyplot(fig)
    plt.close(fig)
else:
    st.info("No data to chart with the current filters.")

# --- Data table -----------------------------------------------------------
st.subheader("Data Table")

display_cols = ["ntaname", "boroname", "hydrant_count", "area_km2", "hydrants_per_km2"]
st.dataframe(
    filtered[display_cols]
    .sort_values("hydrants_per_km2", ascending=False)
    .reset_index(drop=True),
    use_container_width=True,
    column_config={
        "ntaname": "Neighborhood",
        "boroname": "Borough",
        "hydrant_count": st.column_config.NumberColumn("Hydrants", format="%d"),
        "area_km2": st.column_config.NumberColumn("Area (km²)", format="%.2f"),
        "hydrants_per_km2": st.column_config.NumberColumn("Density (/km²)", format="%.1f"),
    },
)

st.download_button(
    label="Download filtered data as CSV",
    data=filtered[display_cols].sort_values("hydrants_per_km2", ascending=False).to_csv(index=False),
    file_name="nyc_hydrant_density_filtered.csv",
    mime="text/csv",
)
# --- Sidebar info ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Data source:** NYC Open Data — "
    "[NTA Neighborhoods](https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd) "
    "and [Hydrants](https://data.cityofnewyork.us/Environment/Hydrants/5bgh-vtsn)"
)
st.sidebar.markdown("**Course:** Modern GIS Accelerator — Lesson 3.5")
